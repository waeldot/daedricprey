import requests
import flask

resp = requests.get("http://www.e-himart.co.kr/app/display/showDisplayShop")
print(resp.headers)
