import requests
import re
import time

API_KEY = 'AIzaSyClRxVPRcjI56KPNTz8GHikFhMh5-LgSYY'
CSE_ID = '54761b2645d0a4960'

def google_search(query, api_key, cse_id):
    url = f'https://www.googleapis.com/customsearch/v1'
    params = {
        'q': query,
        'key': api_key,
        'cx': cse_id,
        'sort': 'date',  # Sort by date to get the most recent results
        'num': 10  # Get up to 10 results
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to retrieve search results. Status code: {response.status_code}")
        return None


def extract_usdt_pairs(text):
    pattern = re.compile(r'\b[A-Z]+/USDT\b')
    return pattern.findall(text)

def main():
    query = 'site:okx.com intitle:delist intitle:spot'
    print("Searching for delist announcements on OKX...")

    while True:
        time.sleep()
        results = google_search(query, API_KEY, CSE_ID)

        if results:
            first_result = results['items'][0]
            print(f"Title: {first_result['title']}")
            print(f"Link: {first_result['link']}\n")

            # Fetch the content of the first article to extract pairs
            article_response = requests.get(first_result['link'], headers={'User-Agent': 'Mozilla/5.0'})
            if article_response.status_code == 200:
                article_text = article_response.text
                usdt_pairs = set(extract_usdt_pairs(article_text))
                transformed_set = {item.replace('/', '-') for item in usdt_pairs}
                filename = '/Users/mac/Downloads/stocks/ex_okx/latest_black_list'
                with open(filename, 'w') as file:
                    for item in transformed_set:
                        file.write(f"{item}\n")
                    print(f"Extracted */USDT pairs: {usdt_pairs}")
            else:
                print(f"Failed to retrieve article content. Status code: {article_response.status_code}")

        else:
            print("No delist announcements found.")

if __name__ == "__main__":
    main()

