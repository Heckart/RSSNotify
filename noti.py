import requests
import time
from bs4 import BeautifulSoup
import feedparser
import datetime
import shelve
from dateutil import parser, tz
from pushbullet import Pushbullet

api_key = "POST YOUR PUSHBULLET API KEY HERE"
file_path = "PUT YOUR FILE PATH FOR WEBSITE PREVIOUS CONTENT HERE"


def parse_date_format2(date_string):
    # Format 2: "Sat, 13 Oct 1917 13:42:49 +0200"
    # Currently used for Vatican feeds
    dt = datetime.datetime.strptime(date_string, "%a, %d %b %Y %H:%M:%S %z")
    timestamp = int(dt.timestamp() * 1000)
    return timestamp

feed_urls = {
    'http://rss.vatican.va/xml/rss_en.xml' : parse_date_format2, # Francis
    'http://press.vatican.va/content/salastampa/en/bollettino.feedrss.xml' : parse_date_format2, # Vatican
  }

latest_article_titles = {
    'http://rss.vatican.va/xml/rss_en.xml': [],
    'http://press.vatican.va/content/salastampa/en/bollettino.feedrss.xml': [],
} 

vatican_articles_not_posted = {
    'Notice of Press Conferences',
    'Notice of Press Conference',
    'Notice from the Office of Litrugical Celebrations',
    'Resignations and Appointments',
    'From the Oriental Churches',
    'General Audience',
    'Audiences',
    'From the Eastern Churches'
}

latest_published_dates_file = 'latest_published_dates.txt'

# Read the txt file and return the contents as a dictionary.
def get_latest_published_dates():
    try:
        with open(latest_published_dates_file, 'r') as file:
            lines = file.readlines()
            return {line.split(',')[0]: int(line.split(',')[1].strip()) if line.split(',')[1].strip() != 'None' else None for line in lines}
    except FileNotFoundError:
        return {} # Return an empty dictionary if the file doesn't exist

# Update the txt file to contain the latest published date in unix millis.
def set_latest_published_date(feed_url, timestamp):
    latest_published_dates = get_latest_published_dates()
    latest_published_dates[feed_url] = timestamp

    with open(latest_published_dates_file, 'w') as file:
        for feed, latest_published_date in latest_published_dates.items():
            file.write(f"{feed},{latest_published_date}\n")

# Access the latest title shelve and return the dictionary.
def load_latest_article_titles():
    try:
        with shelve.open('latest_article_titles') as shelf:
            return shelf.get('titles', {})  # Read the dictionary from the shelf
    except FileNotFoundError:
        return {}  # Return an empty dictionary if the file doesn't exist

# Update the shelve with passed value
def save_latest_article_titles(titles):
    with shelve.open('latest_article_titles') as shelf:
        shelf['titles'] = titles  # Store the dictionary in the shelf


def check_for_new_entries(feed_url, parse_function):
    latest_published_dates = get_latest_published_dates()
    latest_published_date = latest_published_dates.get(feed_url)

    # Parse the RSS feed
    feed = feedparser.parse(feed_url)

    # Load the latest article titles
    latest_article_titles = load_latest_article_titles()
    latest_titles = latest_article_titles.get(feed_url, [])

    # Check if the feed has new entries
    for entry in feed.entries:
        timestamp = parse_function(entry.published)
        
        if latest_published_date is None or timestamp > latest_published_date:
            # Clear the array and add the new title
            latest_titles = [entry.title]
            latest_published_date = timestamp
            print('New Entry Found in', feed_url)
            print('Entry Title:', entry.title)
            print('Entry Published Date:', entry.published)
            print('---')

            # Call the function to post to a subreddit
            # If the article is from a feed where the summary is posted, the summary is passed into the function, 
            # but if the article is not from a feed where the summary is posted, a NULL value is passed in. 
            # This is more space efficient than passing in a long summary that will not be used.
            if (('Communiqu' not in entry.title) and ('Angelus' not in entry) and (entry.title not in vatican_articles_not_posted)):
                send_notification(api_key, entry.title, 1)

        elif timestamp == latest_published_date:
            if entry.title not in latest_titles:
                # New entry with the same timestamp
                print('New Entry Found in', feed_url)
                print('Entry Title:', entry.title)
                print('Entry Published Date:', entry.published, 1)
                print('---')

                # Call the function to post to a subreddit
                if (('Communiqu' not in entry.title) and ('Angelus' not in entry) and (entry.title not in vatican_articles_not_posted)):
                    send_notification(api_key, entry.title, 1)

                # Add the title to the latest titles array
                latest_titles.append(entry.title)

    # Update the latest article titles for the feed
    latest_article_titles[feed_url] = latest_titles

    # Save the latest article titles to the shelf
    save_latest_article_titles(latest_article_titles)

    # Update the latest published date
    set_latest_published_date(feed_url, latest_published_date)

### web parts ###

def fetch_web_page(url):
    response = requests.get(url)
    response.raise_for_status()  # ensures we notice bad responses
    return response.text
    
def load_previous_content(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return None  # Return None if the file doesn't exist
    
def save_new_content(content, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(content)

def has_page_changed(url, old_content):
    new_content = fetch_web_page(url)
    return new_content != old_content

def send_notification(api_key, message, mode):
    # mode 1 = rss mode 2 = webpage
    pb = Pushbullet(api_key)
    if mode == 2:
        pb.push_note("Web Page Changed", message)
    else:
        pb.push_note("New Article", message)



url = "http://gcatholic.org/documents/"
count = 0

while 1:
    count = count + 1

    for feed_url, parse_function in feed_urls.items():
        check_for_new_entries(feed_url, parse_function)
    
    old_content = load_previous_content(file_path)
    if count >= 3: # be nice and only ping their web page every three minutes
        if has_page_changed(url, old_content):
            send_notification("api_key", "Web page has changed!", 2)
            new_content = fetch_web_page(url)
            save_new_content(new_content, file_path)
        count = 0

    time.sleep(60) # be nice, only check every minute

