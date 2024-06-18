import datetime
import os
import re
import zipfile

import win32file, pywintypes
import aiofiles
import httpx
import yaml
from fastapi import APIRouter, Request, Query  # 导入FastAPI组件
from starlette.responses import FileResponse

from app.api.models.APIResponseModel import ErrorResponseModel  # 导入响应模型
from crawlers.hybrid.hybrid_crawler import HybridCrawler  # 导入混合数据爬虫

router = APIRouter()
HybridCrawler = HybridCrawler()

# 读取上级再上级目录的配置文件
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
with open(config_path, 'r', encoding='utf-8') as file:
    config = yaml.safe_load(file)


async def fetch_data(url: str, headers: dict = None):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    } if headers is None else headers.get('headers')
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        print('fetch_data',response)

        # response = await client.get(url, headers=headers,proxies={
        #     'http': 'http://127.0.0.1:7890',
        #     'https': 'http://127.0.0.1:7890'
        # })
        response.raise_for_status()  # 确保响应是成功的
        return response


@router.get("/download", summary="在线下载抖音|TikTok视频/图片/Online download Douyin|TikTok video/image")
async def download_file_hybrid( url: str = Query(
                                   example="https://www.douyin.com/video/7372484719365098803",
                                   description="视频或图片的URL地址，也支持抖音|TikTok的分享链接，例如：https://v.douyin.com/e4J8Q7A/"),
                               prefix: bool = True,
                               with_watermark: bool = False):
    """
    # [中文]
    ### 用途:
    - 在线下载抖音|TikTok 无水印或有水印的视频/图片
    - 通过传入的视频URL参数，获取对应的视频或图片数据，然后下载到本地。
    - 如果你在尝试直接访问TikTok单一视频接口的JSON数据中的视频播放地址时遇到HTTP403错误，那么你可以使用此接口来下载视频。
    - 这个接口会占用一定的服务器资源，所以在Demo站点是默认关闭的，你可以在本地部署后调用此接口。
    ### 参数:
    - url: 视频或图片的URL地址，也支持抖音|TikTok的分享链接，例如：https://v.douyin.com/e4J8Q7A/。
    - prefix: 下载文件的前缀，默认为True，可以在配置文件中修改。
    - with_watermark: 是否下载带水印的视频或图片，默认为False。
    ### 返回:
    - 返回下载的视频或图片文件响应。

    # [English]
    ### Purpose:
    - Download Douyin|TikTok video/image with or without watermark online.
    - By passing the video URL parameter, get the corresponding video or image data, and then download it to the local.
    - If you encounter an HTTP403 error when trying to access the video playback address in the JSON data of the TikTok single video interface directly, you can use this interface to download the video.
    - This interface will occupy a certain amount of server resources, so it is disabled by default on the Demo site, you can call this interface after deploying it locally.
    ### Parameters:
    - url: The URL address of the video or image, also supports Douyin|TikTok sharing links, for example: https://v.douyin.com/e4J8Q7A/.
    - prefix: The prefix of the downloaded file, the default is True, and can be modified in the configuration file.
    - with_watermark: Whether to download videos or images with watermarks, the default is False.
    ### Returns:
    - Return the response of the downloaded video or image file.

    # [示例/Example]
    url: https://www.douyin.com/video/7372484719365098803
    """
    request=None
    if request: 
        # 是否开启此端点/Whether to enable this endpoint
        if not config["API"]["Download_Switch"]:
            code = 400
            message = "Download endpoint is disabled in the configuration file. | 配置文件中已禁用下载端点。"
            return ErrorResponseModel(code=code, message=message, router=request.url.path,
                                  params=dict(request.query_params))

        # 开始解析数据/Start parsing data
        try:
            data = await HybridCrawler.hybrid_parsing_single_video(url, minimal=True)
        except Exception as e:
            code = 400
            return ErrorResponseModel(code=code, message=str(e), router=request.url.path, params=dict(request.query_params))

    try:
        data = await HybridCrawler.hybrid_parsing_single_video(url, minimal=True)
    except Exception as e:  
        print('err',e)
    print('url',url)
    # 开始下载文件/Start downloading files
    try:
        data_type = data.get('type')
        platform = data.get('platform')
        aweme_id = data.get('aweme_id')
        desc = data.get('desc')
        create_time = datetime.datetime.fromtimestamp(data.get('create_time'))  
        author = data.get('author')
        nickname = author.get('nickname')
        sec_uid = author.get('sec_uid')
    
        file_prefix = config.get("API").get("Download_File_Prefix") if prefix else ''
        download_path = os.path.join(config.get("API").get("Download_Path"), f"{platform}_{data_type}")

        desc=desc.strip() + ' '  
        pattern = r'#\w+\s'  
        desc= re.sub(pattern, '', desc)  
        desc = re.sub(r'[<>:"/\\|?*]', '!', desc)  

        print('desc',desc,re.sub(pattern, '', desc)  )
        nickname = re.sub(r'[<>:"/\\|?*]', '!', nickname)  
        with open(os.path.join(config.get("API").get("Download_Path"), 'url_list.txt'), 'a', encoding='utf-8') as file:  
            file.write(f"{nickname}  {url}  {sec_uid}\n")  # 写入昵称并添加换行符  
            # file.write(url + '\n')  # 写入URL并添加换行符（如果URL也应该在新的一行）  

        write_file_path=r'Z:\视频库\Douyin\video'
        # write_file_path=r'E:\DATA\Downloads'
        # 确保目录存在/Ensure the directory exists
        os.makedirs(write_file_path, exist_ok=True)
        # 下载视频文件/Download video file
        if data_type == 'video':
            # file_name = f"{file_prefix}{platform}_{aweme_id}.mp4" if not with_watermark else f"{file_prefix}{platform}_{aweme_id}_watermark.mp4"
            file_name = f"{nickname}_{desc}.mp4"
            file_name= file_name.replace('\n', '')  
            print('file_name',file_name)
            url = data.get('video_data').get('nwm_video_url_HQ') 
            file_path = os.path.join(write_file_path, file_name)
            print('file_path',file_path)
            print('url',url)

            # 获取视频文件
            response = await fetch_data(url) if platform == 'douyin' else await fetch_data(url,
                                                                                           headers=await HybridCrawler.TikTokWebCrawler.get_tiktok_headers())
            # 保存文件
            async with aiofiles.open(file_path, 'wb') as out_file:
                await out_file.write(response.content)
            
            # 打开要修改的文件
            handle = win32file.CreateFile(file_path, win32file.GENERIC_WRITE,
                                        win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                                        None, win32file.OPEN_EXISTING,
                                        win32file.FILE_ATTRIBUTE_NORMAL, None)
            # 设置文件的创建时间和修改时间
            date_time = pywintypes.Time(create_time)
            win32file.SetFileTime(handle, date_time, date_time, None)
            handle.close() # 关闭文件句柄
            # 返回文件内容
            return FileResponse(path=file_path, filename=file_name, media_type="video/mp4")

        # 下载图片文件/Download image file
        elif data_type == 'image':
            print('data_type',data_type,'\n\n')
            # 压缩文件属性/Compress file properties
            zip_file_name = f"{file_prefix}{platform}_{aweme_id}_images.zip" if not with_watermark else f"{file_prefix}{platform}_{aweme_id}_images_watermark.zip"
            zip_file_path = os.path.join(download_path, zip_file_name)

            # 判断文件是否存在，存在就直接返回、
            if os.path.exists(zip_file_path):
                return FileResponse(path=zip_file_path, filename=zip_file_name, media_type="application/zip")

            # 获取图片文件/Get image file
            urls = data.get('image_data').get('no_watermark_image_list') if not with_watermark else data.get(
                'image_data').get('watermark_image_list')
            image_file_list = []
            for url in urls:
                print(url,'\n')
                # 请求图片文件/Request image file
                response = await fetch_data(url)
                print('response',response,'\n')
                index = int(urls.index(url))
                content_type = response.headers.get('content-type')
                file_format = content_type.split('/')[1]
                file_name = f"{file_prefix}{platform}_{aweme_id}_{index + 1}.{file_format}" if not with_watermark else f"{file_prefix}{platform}_{aweme_id}_{index + 1}_watermark.{file_format}"
                file_path = os.path.join(download_path, file_name)
                image_file_list.append(file_path)

                # 保存文件/Save file
                async with aiofiles.open(file_path, 'wb') as out_file:
                    await out_file.write(response.content)
            print('image_file_list',image_file_list,'\n\n')
            # 压缩文件/Compress file
            with zipfile.ZipFile(zip_file_path, 'w') as zip_file:
                for image_file in image_file_list:
                    zip_file.write(image_file, os.path.basename(image_file))

            # 返回压缩文件/Return compressed file
            return FileResponse(path=zip_file_path, filename=zip_file_name, media_type="application/zip")

    # 异常处理/Exception handling
    except Exception as e:
        print(e)
        code = 400
        return ErrorResponseModel(code=code, message=str(e), router=request.url.path, params=dict(request.query_params))
