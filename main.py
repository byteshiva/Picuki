#!/usr/bin/env python3
"""
main.py CLI - Handler
merge dgzr/in-picuki -> motebaya/picuki
20.06.2023 - 8:00 PM 
"""

from typing import Dict, Union
import os
import hashlib
import httpx
from lib.Picuki import Picuki
from lib.logger import logging, logger
from argparse import ArgumentParser, RawTextHelpFormatter
from typing import Dict, List
from rich.console import Console
from rich.panel import Panel
from ssl import SSLWantReadError
from aiohttp import ClientSession
from pathlib import Path as PosixPath
from humanize import naturalsize as get_natural_sizes
import aiofiles, asyncio, os, re, random, time
from rich.progress import (
    Progress, 
    SpinnerColumn, 
    BarColumn, 
    TextColumn, 
    DownloadColumn, 
    TransferSpeedColumn, 
    TimeRemainingColumn
)

def get_valid_filename(url: str) -> str:
    """
    get filename from string url, exit if can't find it
    """
    if (basename := re.search(r"^https?\:\/\/[^<]+\/q\/(?P<filename>[^\"].*?)\|\|", url)):
        basename = list(basename.groupdict().get('filename')[:25])
        random.shuffle(basename)
        basename = "".join(basename)
        return basename
    logger.warning(f"Cannot find spesific name from url: {url}")
    raise ValueError(
        "invalid url"
    )
    
async def _download_media(url: str, username: str, media_type: str, output: str = './'):
    """
    Download media from the given URL and save it to the specified output directory.
    """
    assert url is not None, "Stopped, no URL to download."

    output_folder = os.path.join(os.path.realpath(output), username, media_type)
    
    # Generate a unique filename based on the URL using hashlib
    hash_object = hashlib.md5(url.encode())
    filename = os.path.join(output_folder, hash_object.hexdigest())

    if not os.path.exists(output_folder):
        try:
            os.makedirs(output_folder, exist_ok=True)
        except PermissionError:
            logger.warning(f"Directory output: {output_folder} is not writeable!")
            return
    
    if not os.path.exists(filename):
        Console().print(f"[green] {filename} [green] file exists!")
        # await _download_file_async(url, filename)
    else:
        Console().print(f"[green] Skipping.. [blue]{filename} [green] file exists!")

async def _download_file_async(url: str, filename: str):
    async with ClientSession(headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }) as session:
        try:
            async with session.get(url, timeout=60) as response:  # Set a 60-second timeout (adjust as needed)
                extension = response.headers.get('Content-Type')
                if not extension:
                    raise ValueError(f"Cannot get mimetype of content: {url}")

                filename = f"{filename}.{extension.split('/')[-1]}"
                async with aiofiles.open(filename, "wb") as f:
                    with Progress(
                        SpinnerColumn(speed=1.5),
                        TextColumn("[green] Downloading..", justify="right"),
                        BarColumn(),
                        "[progress.percentage]{task.percentage:>3.0f}%",
                        DownloadColumn(binary_units=False),
                        TransferSpeedColumn(),
                        TimeRemainingColumn(),
                        console=Console(),
                        transient=True
                    ) as progress:
                        task = progress.add_task(
                            "[green] Downloading..",
                            total=int(response.headers.get('content-length', 0))
                        )
                        async for content in response.content.iter_chunks():
                            await f.write(content[0])
                            progress.update(task, advance=len(content[0]))
                        await f.close()
                        progress.stop()
                    Console().print(f"[green] Completed.. saved as: [blue]{filename}")
        except asyncio.TimeoutError:
            # Handle timeout, e.g., print a warning or take other appropriate action
            Console().print("[red]Download timed out.")

def calculate_total_size(username: str) -> Dict[str, int]:
    """
    Calculate the total size of different media types
    """
    total_size: Dict[str, int] = {
        "total": 0,
        "images": 0,
        "videos": 0,
        "thumbnails": 0
    }
    
    fullpath = os.path.realpath(username)
    for glob in PosixPath(fullpath).glob("*"):
        for filename in glob.iterdir():
            media_type = glob.name
            file_size = filename.stat().st_size
            total_size[media_type] += file_size
            total_size["total"] += file_size
    
    return total_size

def show_table(data: Dict[str, Union[str, int]], title: str = None) -> None:
    """
    Show profile data, handling values that can be converted to float
    """
    Console().print(
        Panel.fit(
            '\n'.join(f"[bold]{key}:[/bold] {get_natural_sizes(value) if isinstance(value, int) else value}" for key, value in data.items()),
            title="information" if not title else title,
            border_style="blue"
        )
    )

def calculate_result_and_show_table(username: str) -> None:
    """
    Calculate and display the total size of media types
    """
    total_size = calculate_total_size(username)
    show_table(total_size, title=f"Total Size for {username}")


async def _main(**kwargs):
    """
    Main entry point for the CLI handler
    """
    logging_level = logging.INFO if not kwargs.get('verbose') else logging.getLogger().setLevel(logging.DEBUG)
    
    module = Picuki()
    username = module.clear_username(kwargs.get('username'))
    selected = ['images', 'videos', 'thumbnails']
    
    if not kwargs.get('all'):
        selected = [select for select in selected if kwargs.get(select)]

    profile = await module.get_profile(username)

    if not profile:
        logger.warning(f"Cannot find user: @{username}, check the username")
        return

    page, result = profile
    show_table(result)

    await module.get_media_id(page, logger)
    
    if not module.media_id:
        logger.warning(f"The user: {profile.get('username')} doesn't have any posts.")
        return
    
    logger.info(f"Total Media Collected: {len(module.media_id)}")
    logger.info(f"Selected media: {selected}, starting download..")

    for index, media in enumerate(module.media_id, 1):
        logger.info(f"Getting content from: {media} [{index} of {len(module.media_id)}]")
        try:
            content = await module.get_media_content(media)
            if content:
                _media = content.pop('media')
                show_table(content)

                if 'images' in selected:
                    images = _media.get('images')
                    if images:
                        logger.info(f"Total images collected: {len(images)}")
                        for img_index, img in enumerate(images, 1):
                            logger.info(f"Downloading images ({img_index} of {len(images)})")
                            await _download_media(
                                url=img,
                                username=username,
                                media_type="images",
                                output="images"
                            )
                    else:
                        logger.warning('There are no images to download!')
                
                if 'videos' in selected or 'thumbnails' in selected:
                    videos = _media.get('videos')
                    if videos:
                        logger.info(f"Total videos/thumbnails Collected: {len(videos)}")
                        for vid_index, vids in enumerate(videos, 1):
                            if 'thumbnails' in selected:
                                logger.info(f"Downloading thumbnails ({vid_index} of {len(videos)})")
                                await _download_media(
                                    url=vids.get('thumbnail'),
                                    username=username,
                                    media_type="thumbnails",
                                    output="thumbnails"
                                )

                            if 'videos' in selected:
                                logger.info(f"Downloading videos ({vid_index} of {len(videos)})")
                                await _download_media(
                                    url=vids.get('url'),
                                    username=username,
                                    media_type="videos",
                                    output="videos"
                                )
                    else:
                        logger.warning("There are no videos or thumbnails to download..")
                    
                time.sleep(1)
            else:
                logger.warning(f"Cannot get content from media ID: {media}")
        except (httpx.ReadTimeout, asyncio.exceptions.CancelledError, SSLWantReadError) as e:
            logger.warning(f"Exception: {str(e)}, in media ID: {media}")
            time.sleep(1)
            continue
        except (asyncio.exceptions.CancelledError, SSLWantReadError) as e:
            logger.warning(f"Exception: {str(e)}, in media ID: {media}")
            time.sleep(1)
            continue

    calculate_result_and_show_table(username)

if __name__ == "__main__":
    parser = ArgumentParser(
        description="\t\tPicuki.com\n  [Instagram bulk profile media downloader]\n\t    @github.com/motebaya", 
        formatter_class=RawTextHelpFormatter
    )
    parser.add_argument("-u", "--username", help="specific Instagram username", metavar="")
    parser.add_argument("-i", "--images", help="just download all images", action="store_true")
    parser.add_argument("-v", "--videos", help="just download all videos", action="store_true")
    parser.add_argument("-t", "--thumbnails", help="just download all videos thumbnails", action="store_true")
    parser.add_argument("-a", "--all", help="download all media", action="store_true")
    
    opt = parser.add_argument_group("Optional")
    opt.add_argument("-V", "--verbose", help="enable logger debug mode", action="store_true")
    args = parser.parse_args()

    if args.username and any([args.images, args.videos, args.thumbnails, args.all, args.verbose]):
        try:
            asyncio.run(_main(**vars(args)))
        except (asyncio.exceptions.CancelledError, SSLWantReadError) as e:
            logger.warning(f"Exception: {str(e)}")
    else:
        parser.print_help()
   
