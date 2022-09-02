import dataclasses
import datetime
import time
from dataclasses import dataclass

import cssutils
import requests
import yaml
from bs4 import BeautifulSoup


@dataclass
class Message:
    timestamp: int
    text: str
    photo: str = None
    author: str = None
    profile_picture: str = None
    channel_id: str = None
    color: int = None


class Scraper:
    def __init__(self, id: str, color: int = None):
        self.id = id
        self.color = color
        if self.color is None:
            self.color = int.from_bytes(self.id.encode(), "big") % 0x1000000

    def get_messages(self):
        url = f"https://t.me/s/{self.id}"
        r = requests.get(url)
        soup = BeautifulSoup(r.content, "html.parser")

        message_elements = soup.find_all("div", {"class": "tgme_widget_message_wrap"})
        messages = []

        for message in message_elements:
            message_text_element = message.find(
                "div", {"class": "tgme_widget_message_text"}
            )
            for e in message_text_element.find_all("br"):
                e.replace_with("\n")
            for e in message_text_element.find_all("a"):
                text = e.text
                href = e.get("href")
                e.replace_with(f"[{text}]({href})")
            message_text = message_text_element.text

            photo_wrap = message.find("a", {"class": "tgme_widget_message_photo_wrap"})
            photo = None
            if photo_wrap is not None:
                photo_wrap_css = photo_wrap["style"]
                css = cssutils.parseStyle(photo_wrap_css)
                url = css.backgroundImage[4:-1]
                photo = url

            author_element = message.find(
                "div", {"class": "tgme_widget_message_author"}
            )
            author = None
            if author_element is not None:
                author = author_element.text

            profile_picture_element = message.find(
                "div", {"class": "tgme_widget_message_user"}
            )
            profile_picture = None
            if profile_picture_element is not None:
                profile_picture_image = profile_picture_element.find("img")
                profile_picture = profile_picture_image.get("src")

            time_element = message.find("a", {"class": "tgme_widget_message_date"})
            time_string = time_element.find("time")["datetime"]
            timestamp = datetime.datetime.strptime(
                time_string, "%Y-%m-%dT%H:%M:%S%z"
            ).timestamp()

            messages.append(
                Message(
                    text=message_text,
                    photo=photo,
                    author=author,
                    profile_picture=profile_picture,
                    timestamp=timestamp,
                    channel_id=self.id,
                    color=self.color,
                )
            )

        return messages


class Sender:
    def __init__(self, webhook_url):
        self.webhook = webhook_url

    def send_message(self, message: Message):
        requests.post(
            self.webhook,
            json={
                "embeds": [
                    {
                        "description": message.text,
                        "image": {"url": message.photo},
                        "color": message.color,
                        "timestamp": datetime.datetime.fromtimestamp(
                            message.timestamp
                        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                ],
                "username": message.author,
                "avatar_url": message.profile_picture,
            },
        )


class Link:
    def __init__(self, senders, scrapers) -> None:
        self.senders = senders
        self.scrapers = scrapers

        self.load()

    def load(self):
        try:
            with open("sent.yaml", "r") as f:
                messages = yaml.safe_load(f)
            self.messages = [Message(**message) for message in messages]
        except FileNotFoundError:
            self.messages = []

    def dump(self):
        messages = [dataclasses.asdict(message) for message in self.messages]
        yaml.safe_dump(messages, open("sent.yaml", "w"))

    def retranslate(self):
        messages = sum((scraper.get_messages() for scraper in self.scrapers), [])
        messages.sort(key=lambda msg: msg.timestamp)
        for message in messages:
            for sender in self.senders:
                if message not in self.messages:
                    sender.send_message(message)
                    self.messages.append(message)
        self.dump()


def main():
    config = yaml.safe_load(open("config.yaml", "r"))
    links = []
    for link in config:
        links.append(
            Link(
                [Sender(sender) for sender in link["senders"]],
                [Scraper(scraper) for scraper in link["scrapers"]],
            )
        )

    while True:
        for link in links:
            link.retranslate()
        time.sleep(600)


if __name__ == "__main__":
    main()
