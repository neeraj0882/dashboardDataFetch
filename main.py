import logging
from prometheus_client import start_http_server
from prometheus_client import CollectorRegistry, write_to_textfile
from prometheus_client.core import REGISTRY, GaugeMetricFamily
import requests
import time
from lxml import html
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET
import re
import datetime


RE_WSP = re.compile(r'\s+', re.U)

bamboo_base_url = 'https://dcbamboo.service.dev:8443'
bamboo_api_url = bamboo_base_url + '/rest/api/latest'
bamboo_test_url = bamboo_base_url + '/browse/'


session = requests.Session()
session.verify = False
session.auth = ('uid', 'pwd')


config = [
		
	{
		'job_key': 'job_key',
		'branch': 'develop',
		'name': 'job name',
		'application': 'appname',
		'test_type': 'test name',
	}
]


bamboo_test_categories = [
	'successful',
	'failed',
	'quarantined',
	'skipped'
]

def format_test_count(text):
	if len(text)>=4:
		for k in text:
			if k==",":
				text=text.replace(',','')
				count = int(text)
				print count
	else:
		count = int(text)
	return count


def calculate_pass_percentage(passed,total):
	if total == 0:
		total = 1
	passed = float(passed)
	total = float(total)
	percentage = (passed / total) * 100
	percentage = "{0:0.1f}".format(percentage)
	percentage = float(percentage)
	return percentage

def parse_formatted_time(s):
	parts = RE_WSP.split(s)
	i = 0
	if parts[0] == '':
		i += 1
	n = len(parts)
	if parts[n - 1] == '':
		n -= 1
	if i < n and parts[i] == '<':
		i += 1
	seconds = 0
	while i < n:
		try:
			quantity = int(parts[i])
		except:
			#seconds = 1
			seconds = 0
			break
		if i + 1 == n:
			raise ValueError()
		unit = parts[i + 1]
		if unit == 'second' or unit == 'seconds':
			seconds += quantity
		elif unit == 'minutes' or unit == 'minute':
			seconds += quantity * 60
		else:
			raise NotImplementedError('Error while parsing execution time, unit not supported: ' + unit + '. Please update this code.')
		i += 2
	return seconds

def extract_execution_time(str):
	parts = str.split(" ")
	try:
		time = int(parts[0])
	except:
		#print 'not a correct time string'
		return 0
	if parts[1] == 'minutes' or parts[1] == 'minute':
		time = time * 60
	elif parts[1] == 'seconds' or parts[1] == 'second':
		time = time
	return time

class BambooTestCountCollector(object):
	def collect(self):
		gmf_test_counts = GaugeMetricFamily('testCountCategories', 'Documentation of test_counts metric, TODO make this a proper description', 
			labels=['category', 'branch', 'name','application','testType'])
		gmf_total_tests = GaugeMetricFamily('totalTests', 'Documentation of test_counts metric, TODO make this a proper description', 
			labels=['branch', 'name','application','testType','recentCount'])
		gmf_test_excution_time = GaugeMetricFamily('testExecutionTime', 'In seconds. Documentation of test execution time metric, TODO make this a proper description',
			labels=['branch', 'name','application','testType','lastRunDate','buildStatus'])
		gmf_test_pass_percentage = GaugeMetricFamily('testPassPercentage', 'In percent. Documentation of test execution time metric, TODO make this a proper description',
			labels=['branch', 'name','application','testType','lastRunDate','buildStatus','executionTimeSec'])
		gmf_test_status = GaugeMetricFamily('testFlag', 'In percent. Documentation of test execution time metric, TODO make this a proper description',
			labels=['branch', 'name','application','testType','lastRunDate','buildStatus','executionTimeSec','passPercentage'])
		gmf_successtest_counts = GaugeMetricFamily('testStatus_previousBuilds', 'In number. Documentation of test execution time metric, TODO make this a proper description',
			labels=['branch', 'name','application','testType','lastRunDate','buildStatus','passPercentage','buildNumber'])
		gmf_passpercent_previous = GaugeMetricFamily('testPassPercentage_previousBuilds', 'In number. Documentation of test execution time metric, TODO make this a proper description',
			labels=['branch', 'name','application','testType','lastRunDate','buildStatus','buildNumber'])
		gmf_executionTime_previous = GaugeMetricFamily('testExecutionTime_previousBuilds', 'In sec. Documentation of test execution time metric, TODO make this a proper description',
			labels=['branch', 'name','application','testType','lastRunDate','buildStatus','buildNumber'])
		for item in config:
			job_key = item['job_key']
			response = session.get(bamboo_api_url + '/result/' + job_key + '/latest?expand=results.result')
			#urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
			response.raise_for_status()
			root = ET.fromstring(response.text)
			bamboo_test_counts = {}
			passed_tests = int(root.find('successfulTestCount').text)
			failed_tests = int(root.find('failedTestCount').text)
			quarantined_tests = int(root.find('quarantinedTestCount').text)
			skipped_tests = int(root.find('skippedTestCount').text)
			all_tests = passed_tests+failed_tests+quarantined_tests+skipped_tests
			percentage_pass = calculate_pass_percentage(passed_tests,all_tests)
			#print percentage_pass
			build_state = root.find('buildState').text
			Tests = -1	
			Status = 'Fail'		
			if build_state=='Successful':
				Tests = 1
				Status = 'Pass'
			if build_state=='Failed' and passed_tests>=1 and failed_tests==0:
				Tests = 1
				Status = 'Pass'
			print '############# Status'
			print Status						
			build_result_key = root.find('buildResultKey').text
			page = session.get(bamboo_test_url + build_result_key + '/test')
			tree = html.fromstring(page.content)
			execution_time_formatted = tree.xpath('//li[@id="testsSummaryDuration"]/strong/text()')
			print extract_execution_time
			#execution_time = parse_formatted_time(execution_time_formatted[0])
			execution_time = extract_execution_time(execution_time_formatted[0])
			#print execution_time
			total_execution_time = str(execution_time)+" sec"
			element_build_completed_time = root.find('prettyBuildCompletedTime')
			last_run = element_build_completed_time.text
			gmf_test_excution_time.add_metric([
				item['branch'],	
				item['name'],
				item['application'],
				item['test_type'],
				last_run,
				build_state
			], execution_time)
			total_tests_formatted = tree.xpath('//li[@id="testsSummaryTotal"]/strong/text()')
			total_tests_count = format_test_count(total_tests_formatted[0])

			if total_tests_count==0:						
				for i in range(1,10):
					build_result_key_formatted = build_result_key.split("-")
					build_key_parts = build_result_key_formatted
					length = len(build_result_key_formatted)
					last_item = build_result_key_formatted[length-1]
					last_build_key = int(build_result_key_formatted[len(build_result_key_formatted)-1]) - 1
					build_result_key = build_result_key.replace(last_item,str(last_build_key))
					page = session.get(bamboo_test_url + build_result_key + '/test')
					tree = html.fromstring(page.content)
					total_tests_formatted = tree.xpath('//li[@id="testsSummaryTotal"]/strong/text()')
					try:
						total_tests_count = format_test_count(total_tests_formatted[0])
					except:
						i=i-1			
					if total_tests_count !=0:
						break
			#print total_tests_count
			if total_tests_count==all_tests:
				tests_equal_flag = True
			else:
				tests_equal_flag = False
			#print tests_equal_flag
			recent_count = str(tests_equal_flag)
			gmf_test_pass_percentage.add_metric([
				item['branch'],	
				item['name'],
				item['application'],
				item['test_type'],
				last_run,
				build_state,
				total_execution_time,				
			], percentage_pass)

			gmf_test_status.add_metric([
				item['branch'],	
				item['name'],
				item['application'],
				item['test_type'],
				last_run,
				build_state,
				total_execution_time,
				str(percentage_pass)				
			], Tests)

			gmf_total_tests.add_metric([
					item['branch'],	
					item['name'],
					item['application'],	
					item['test_type'],
					recent_count,	
				], total_tests_count)


			for c in bamboo_test_categories:
				element = root.find(c + 'TestCount')
				bamboo_test_counts[c] = int(element.text)
				
			for c in bamboo_test_counts:
				gmf_test_counts.add_metric([
					c,
					item['branch'],	
					item['name'],
					item['application'],	
					item['test_type'],	
				], bamboo_test_counts[c])


			##Get results for last 5 builds##
			lastNResponses = session.get(bamboo_api_url + '/result/' + job_key + '?expand=results[0:4].result')
			root_n = ET.fromstring(lastNResponses.text)
			el = root_n.find('results')
			for a in el:
				buildNum = int(a.find('buildNumber').text)
				el_passed_tests = int(a.find('successfulTestCount').text)
				el_failed_tests = int(a.find('failedTestCount').text)
				el_quarantined_tests = int(a.find('quarantinedTestCount').text)
				el_skipped_tests = int(a.find('skippedTestCount').text)
				el_all_tests = el_passed_tests+el_failed_tests+el_quarantined_tests+el_skipped_tests
				el_percentage_pass = calculate_pass_percentage(el_passed_tests,el_all_tests)
				build_result_key = a.find('buildResultKey').text
				page = session.get(bamboo_test_url + build_result_key + '/test')
				tree = html.fromstring(page.content)
				execution_time_formatted = tree.xpath('//li[@id="testsSummaryDuration"]/strong/text()')
				execution_time_prev = extract_execution_time(execution_time_formatted[0])
				print 'execution time for build_result_key# '+build_result_key+' for build# '+str(buildNum)+': '+str(execution_time_prev)
				#print a.find('buildNumber').text
				#print a.find('successfulTestCount').text
				el_lastRun = a.find('prettyBuildCompletedTime').text
				el_lastRun_formatted = datetime.datetime.strptime(el_lastRun, '%a, %d %b, %H:%M %p')
				#print el_lastRun_formatted
				date_formatted = el_lastRun_formatted.strftime("%d/%m %H:%M %p")
				#print date_formatted
				el_buildState = a.find('buildState').text
				gmf_successtest_counts.add_metric([
					item['branch'],	
					item['name'],
					item['application'],
					item['test_type'],
					el_lastRun,
					#date_formatted,
					el_buildState,
					str(el_percentage_pass),
					str(buildNum),
				], el_passed_tests)
				gmf_passpercent_previous.add_metric([
					item['branch'],	
					item['name'],
					item['application'],
					item['test_type'],
					el_lastRun,
					#date_formatted,
					el_buildState,
					str(buildNum),
				], el_percentage_pass)
				gmf_executionTime_previous.add_metric([
					item['branch'],	
					item['name'],
					item['application'],
					item['test_type'],
					el_lastRun,
					#date_formatted,
					el_buildState,
					str(buildNum),
				], execution_time_prev)



			
		yield gmf_test_counts
		yield gmf_test_excution_time
		yield gmf_test_pass_percentage
		yield gmf_test_status
		yield gmf_total_tests
		yield gmf_successtest_counts
		yield gmf_passpercent_previous
		yield gmf_executionTime_previous

logging.basicConfig(level=logging.DEBUG, format='%(message)s')
registry = CollectorRegistry()
REGISTRY.register(BambooTestCountCollector())
registry.register(BambooTestCountCollector())
write_to_textfile('result.prom', registry)
logging.info('Done collecting...')
start_http_server(9100)
#start_http_server(9300)
while True:
	time.sleep(1)


#push_to_gateway('localhost:9091', job='batchA', registry=registry)
