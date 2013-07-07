# PyAlgoTrade
# 
# Copyright 2013 Gabriel Martin Becedillas Ruiz
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#   http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
.. moduleauthor:: Gabriel Martin Becedillas Ruiz <gabriel.becedillas@gmail.com>
"""

import urllib
import datetime
import json

import pyalgotrade.logger
from pyalgotrade.utils import dt

logger = pyalgotrade.logger.getLogger("mtgox")

def timestamp_to_tid(unixTime):
	return unixTime * 1000000

def datetime_to_tid(dateTime):
	unixTime = dt.datetime_to_timestamp(dt.as_utc(dateTime))
	return timestamp_to_tid(unixTime)

def tid_to_datetime(tid):
	unixTime = int(tid) / 1000000.0
	return dt.timestamp_to_datetime(unixTime)

# https://en.bitcoin.it/wiki/MtGox/API#Number_Formats
def from_value_int(currency, value_int):
	currency = currency.upper()
	ret = int(value_int)
	if currency in ["JPY", "SEK"]:
		ret = ret * 0.001
	elif currency == "BTC":
		ret = ret * 0.00000001
	else:
		ret = ret * 0.00001
	return ret

def from_amount_int(value_int):
	return int(value_int) * 0.00000001

class Trade:
	def __init__(self, trade):
		self.__tradeId = int(trade["tid"])
		self.__dateTime = tid_to_datetime(trade["tid"])
		currency = trade["price_currency"]
		self.__price = from_value_int(currency, trade["price_int"])
		self.__amount = from_amount_int(trade["amount_int"])
		self.__type = trade["trade_type"]

	def getId(self):
		return self.__tradeId

	def getDateTime(self):
		return self.__dateTime

	def getPrice(self):
		return self.__price

	def getAmount(self):
		return self.__amount

	def getType(self):
		return self.__type

class Trades:
	def __init__(self, trades):
		self.__first = None
		self.__last = None
		self.__trades = []

		for trade in trades:
			# From https://en.bitcoin.it/wiki/MtGox/API/HTTP/v1:
			# A trade can appear in more than one currency, to ignore duplicates,
			# use only the trades having primary =Y
			if trade["primary"] != "Y":
				continue
			tradeObj = Trade(trade)
			self.__trades.append(tradeObj)

			# Store first and last trades.
			if self.__first == None or tradeObj.getId() < self.__first.getId():
				self.__first = tradeObj
			if self.__last == None or tradeObj.getId() > self.__last.getId():
				self.__last = tradeObj

	def getFirst(self):
		return self.__first

	def getLast(self):
		return self.__last

	def getTrades(self):
		return self.__trades

class TradesFile:
	def __init__(self, csvFile):
		self.__f = open(csvFile, "w")
		self.__f.write("id,price,amount,type\n")
		self.__f.flush()

	def addTrades(self, trades):
		for trade in trades:
			self.__f.write("%s,%s,%s,%s\n" % (trade.getId(), trade.getPrice(), trade.getAmount(), trade.getType()))
		self.__f.flush()

def download_trades_impl(currency, tid):
	url = "https://data.mtgox.com/api/1/BTC%s/trades?since=%d" % (currency.upper(), tid)

	f = urllib.urlopen(url)
	buff = f.read()
	if f.headers["Content-Type"].find("application/json") != 0:
		logger.error(buff)
		raise Exception("Failed to download data. Invalid Content-Type: %s" % (f.headers["Content-Type"]))
	response = json.loads(buff)
	if response["result"] != "success":
		raise Exception("Failed to download data. Result '%s'" % (response["result"]))
	return response

def download_trades_since(currency, tid, retries=3):
	logger.info("Downloading trades since %s." % (tid_to_datetime(tid)))
	# logger.info("Downloading trades since %d." % (tid))

	done = False
	while not done:
		try:
			response = download_trades_impl(currency, tid)
			done = True
		except Exception, e:
			if retries == 0:
				raise e
			else:
				logger.error("%s. Retrying..." % (e))
				retries -= 1

	ret =  Trades(response["return"])
	logger.info("Got %d trades." % (len(ret.getTrades())))
	return ret

def download_trades(tradesFile, currency, tidBegin, tidEnd):
	nextTid = tidBegin

	done = False
	while not done:
		trades = download_trades_since(currency, nextTid)
		if len(trades.getTrades()) == 0:
			done = True
		# The last trade is smaller than lastTid, we need to get more trades right after that one.
		elif trades.getLast().getId() < tidEnd:
			tradesFile.addTrades(trades.getTrades())
			nextTid = trades.getLast().getId() + 1
		# We went beyond last trade. Only store the appropriate ones.
		else:
			done = True
			tradeItems = []
			for trade in trades.getTrades():
				if trade.getId() < tidEnd:
					tradeItems.append(trade)
			tradesFile.addTrades(tradeItems)

def download_trades_by_year(currency, year, csvFile):
	"""Download trades for a given year.

	:param currency: Currency in which trade was completed.
	:type currency: string.
	:param year: The year.
	:type year: int.
	:param csvFile: The path to the CSV file to write the trades.
	:type csvFile: string.

	.. note::
		This will take some time since Mt. Gox API returns no more than 1000 trades on each request
	"""

	# Calculate the first and last trade ids for the year.
	begin = datetime.datetime(year, 1, 1)
	end = datetime.datetime(year+1, 1, 1)
	tidBegin = datetime_to_tid(begin)
	tidEnd = datetime_to_tid(end)

	tradesFile = TradesFile(csvFile)
	download_trades(tradesFile, currency, tidBegin, tidEnd)

def download_trades_by_month(currency, year, month, csvFile):
	"""Download trades for a given month.

	:param currency: Currency in which trade was completed.
	:type currency: string.
	:param year: The year.
	:type year: int.
	:param month: The month.
	:type month: int.
	:param csvFile: The path to the CSV file to write the trades.
	:type csvFile: string.

	.. note::
		This will take some time since Mt. Gox API returns no more than 1000 trades on each request
	"""

	# Calculate the first and last trade ids for the year.
	begin = datetime.datetime(year, month, 1)
	if month == 12:
		end = datetime.datetime(year+1, 1, 1)
	else:
		end = datetime.datetime(year, month + 1, 1)
	tidBegin = datetime_to_tid(begin)
	tidEnd = datetime_to_tid(end)

	tradesFile = TradesFile(csvFile)
	download_trades(tradesFile, currency, tidBegin, tidEnd)

def download_trades_by_day(currency, year, month, day, csvFile):
	# Calculate the first and last trade ids for the year.
	begin = datetime.datetime(year, month, day)
	end = begin + datetime.timedelta(days=1)
	tidBegin = datetime_to_tid(begin)
	tidEnd = datetime_to_tid(end)

	tradesFile = TradesFile(csvFile)
	download_trades(tradesFile, currency, tidBegin, tidEnd)
