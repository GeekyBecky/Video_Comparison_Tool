import datetime
import json
import os
import re

from google.cloud import storage
from google.oauth2 import service_account


def pair_after_and_previous(storage_client, bucket_name):
    blobs = storage_client.list_blobs(bucket_name)

    after_dict = {}
    prev_dict = {}

    pattern = re.compile(r"_(\d+)\.mp4$")

    for blob in blobs:
        filename = blob.name
        match = pattern.search(filename)
        if match:
            index = match.group(1)
            if "after/" in filename:
                after_dict[index] = filename
            elif "prev/" in filename:
                prev_dict[index] = filename

    matched_pairs = []
    for index, after_file in after_dict.items():
        if index in prev_dict:
            matched_pairs.append((prev_dict[index], after_file))

    return matched_pairs


def generate_download_signed_url_v4(bucket_name):
    """Generates a v4 signed URL for downloading a blob.

    Note that this method requires a service account key file. You can not use
    this if you are using Application Default Credentials from Google Compute
    Engine or from the Google Cloud SDK.
    """
    gcs_key_json = os.environ.get("GCS_SIGNEDURL_KEY")
    if not gcs_key_json:
        raise ValueError("GCS_SIGNEDURL_KEY is not set in environment variables.")

    credentials_dict = json.loads(gcs_key_json)
    credentials = service_account.Credentials.from_service_account_info(credentials_dict)

    storage_client = storage.Client(credentials=credentials, project=credentials_dict["project_id"])

    video_data = []
    for prev_blob_name, after_blob_name in pair_after_and_previous(storage_client, bucket_name):
        bucket = storage_client.bucket(bucket_name)
        prev_blob = bucket.blob(prev_blob_name)
        after_blob = bucket.blob(after_blob_name)

        prev_url = prev_blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="GET",
        )

        after_url = after_blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="GET",
        )
        video_data.append({"prev": prev_url, "after": after_url})

    return video_data


generate_download_signed_url_v4("evaluation_set")


def generate_html(video_data):
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Video Comparison</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                text-align: center;
                margin: 20px;
            }}

            .video-container {{
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-top: 20px;
            }}

            video {{
                width: 100%;
                max-height: 550px;
                border: 2px solid #ccc;
                border-radius: 5px;
            }}

            .progress {{
                margin-top: 10px;
                font-size: 18px;
            }}

            .buttons {{
                margin-top: 20px;
            }}

            button {{
                padding: 10px 15px;
                font-size: 16px;
                margin: 5px;
                cursor: pointer;
            }}

            button:disabled {{
                opacity: 0.5;
                cursor: not-allowed;
            }}
        </style>
    </head>

    <body>
        <h1>Video Comparison Tool</h1>
        <div class="progress" id="progress-info">
            Video 1 of {len(video_data)}
        </div>

        <div class="video-container" id="video-container"></div>
        <div class="buttons">
            <button id="prev-video" onclick="loadPreviousVideos()" disabled>Previous Videos</button>
            <button id="next-video" onclick="loadNextVideos()">Next Videos</button>
        </div>

        <script>
            const videoData = {json.dumps(video_data)};
            let currentIndex = 0;

            function loadVideos(index) {{
                if (index >= videoData.length) {{
                    document.getElementById("progress-info").textContent = "No more videos.";
                    return;
                }}

                const videoContainer = document.getElementById("video-container");
                videoContainer.innerHTML = `
                    <div class="video-wrapper">
                        <h3>Previous</h3>
                        <video controls>
                            <source src="${{videoData[index].prev}}" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                    </div>
                    <div class="video-wrapper">
                        <h3>After</h3>
                        <video controls>
                            <source src="${{videoData[index].after}}" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                    </div>
                `;

                document.getElementById("progress-info").textContent = `Video ${{index + 1}} of ${{videoData.length}}`;
                document.getElementById("prev-video").disabled = index === 0;
                document.getElementById("next-video").disabled = index === videoData.length - 1;
            }}

            function loadNextVideos() {{
                if (currentIndex < videoData.length - 1) {{
                    currentIndex++;
                    loadVideos(currentIndex);
                }}
            }}

            function loadPreviousVideos() {{
                if (currentIndex > 0) {{
                    currentIndex--;
                    loadVideos(currentIndex);
                }}
            }}

            window.onload = () => loadVideos(currentIndex);
        </script>
    </body>
    </html>
    """

    with open("pr-branch/index.html", "w", encoding="utf-8") as f:
        f.write(html_template)

    print("HTML file generated: index.html")


if __name__ == "__main__":
    bucket_name = "evaluation_set"
    video_data = generate_download_signed_url_v4(bucket_name)
    generate_html(video_data)
