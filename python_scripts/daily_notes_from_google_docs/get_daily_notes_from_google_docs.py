import os.path
import io
import zipfile
import shutil
import json
from pathlib import Path
import datetime

# import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

import html2text

# get file path
file_path = Path(__file__).resolve().parent

app_config = {}
with open(Path(file_path,"app_config.json"), "r") as f:
    app_config = json.load(f)

with open(Path(file_path,app_config["secrets"]["secrets_folder"],app_config["secrets"]["document_secrets"]), "r") as f:
    _document_id = json.load(f)
    app_config["document_id"] = _document_id["document_id"]

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/drive.file"]

DOCUMENT_ID = app_config["document_id"]


def main():
  """Shows basic usage of the Drive v3 API.
  Prints the names and ids of the first 10 files the user has access to.
  """
  creds = None
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  token_file = f"{file_path}/{app_config['secrets']['secrets_folder']}/{app_config['secrets']['token_file']}"
  credentials_file = f"{file_path}/{app_config['secrets']['secrets_folder']}/{app_config['secrets']['credentials_file']}"
  
  if os.path.exists(token_file):
    creds = Credentials.from_authorized_user_file(token_file, SCOPES)
  # If there are no (valid) credentials available, let the user log in.
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            credentials_file, SCOPES
        )
    #   creds = flow.run_local_server(port=0)
        creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')
    # Save the credentials for the next run
    with open(token_file, "w") as token:
      token.write(creds.to_json())

  try:
    service = build("drive", "v3", credentials=creds)
    service2 = build("docs", "v1", credentials=creds)

    file_id = DOCUMENT_ID

    download_file_as_html(service, file_id)

    html_filename = unzip_and_get_filename()

    markdown_content = convert_html_to_markdown(html_filename)

    markdown_filename = ""
    
    if app_config["get_filename_from_document"]:
       markdown_filename = save_markdown_to_file(markdown_content, html_filename)
    else:
        markdown_filename = save_markdown_to_file(markdown_content)

    # delete the downloaded files
    os.remove("downloaded_document.zip")
    # delete the downloaded files
    shutil.rmtree("downloaded_document")
    print("Downloaded files deleted.")

    if app_config["clear_document_after_download"]:
        # clear the document
        clear_document(service2, DOCUMENT_ID)

  except HttpError as error:
    # TODO(developer) - Handle errors from drive API.
    print(f"An error occurred: {error}")

def download_file_as_html(service, file_id):
    try:
      # pylint: disable=maybe-no-member
      request = service.files().export_media(
          fileId=file_id, mimeType="application/zip"
      )
      file = io.BytesIO()
      downloader = MediaIoBaseDownload(file, request)
      done = False
      while done is False:
        status, done = downloader.next_chunk()
        print(f"Download {int(status.progress() * 100)}.")
      with open("downloaded_document.zip", "wb") as f:
        f.write(file.getvalue())
      print("Download complete.")
    except HttpError as error:
      # TODO(developer) - Handle errors from drive API.
      print(f"An error occurred: {error}")

def clear_document(service, document_id):
    try:
        # clear the document content
        service.documents().get(documentId=document_id).execute()
        # get the last index of the document
        last_index = 0
        result = service.documents().get(documentId=document_id).execute()
        for element in result.get("body").get("content"):
            # print(f"{element}")
            last_index = element.get("endIndex")
        print(f"Last index: {last_index}")

        # Update the document with empty content
        requests = [
            {
                'deleteContentRange': {
                    'range': {
                        'startIndex': 1,
                        'endIndex': last_index - 1,
                    }

                }

            },
        ]
        result = service.documents().batchUpdate(
            documentId=document_id, body={'requests': requests}).execute()
        print("Document content cleared.")
    except HttpError as error:
        # TODO(developer) - Handle errors from drive API.
        print(f"An error occurred: {error}")

def unzip_and_get_filename():
    with zipfile.ZipFile("downloaded_document.zip", "r") as zip_ref:
        zip_ref.extractall("downloaded_document")
    print("Unzip complete.")
    # get the name of the html file
    html_file = None
    for file in os.listdir("downloaded_document"):
        if file.endswith(".html"):
            html_file = file.split(".")[0]
            break
    return html_file

def convert_html_to_markdown(html_filename):
    # parse the document and save as markdown file using html2text
    with open(f"downloaded_document/{html_filename}.html", "r") as f:
        text_content = f.read()
    converter = html2text.HTML2Text()
    markdown_content = converter.handle(text_content)
    return markdown_content

def save_markdown_to_file(markdown_content, html_filename="daily_notes"):
    # get the defined directory name from the app_config
    directory_name = app_config["imported_document_folder"]
    # check if the directory name is empty, and if so set it to the current directory
    if directory_name == "":
        directory_name = "."       
    # check if the directory exists
    if not os.path.exists(directory_name):
        os.makedirs(directory_name)

    # save the markdown content to a file with the same name as the html file + current date in YYYY-MM-DD format
    html_filename = f"{directory_name}/{html_filename}-{datetime.datetime.now().strftime('%Y-%m-%d')}"
    # check if the file already exists
    if os.path.exists(f"{html_filename}.md"):
        print("File already exists.")
        with open(f"{html_filename}.md", "r") as f:
            existing_content = f.read()
        # check if the file content contains the content passed as argument
        if markdown_content in existing_content:
            print("Content already exists in the file.")
            return html_filename
        else:
            print("Content does not exist in the file. Appending content.")
            with open(f"{html_filename}.md", "a") as f:
                f.write(markdown_content)
    else:
        print("File does not exist. Creating file.")
        with open(f"{html_filename}.md", "w") as f:
            f.write(markdown_content)

    print("Saving of markdown file complete.")

    return html_filename

if __name__ == "__main__":
  main()