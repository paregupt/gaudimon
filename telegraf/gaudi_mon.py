#! /usr/bin/python3
"""Gather information from Intel Gaudi Servers and print output in the
desired output format"""

__author__ = "Paresh Gupta"
__version__ = "1.00"
__updated__ = "21-Jul-2024-10-PM-PDT"

import sys
import os
import argparse
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import json
import re
from ipaddress import IPv4Interface

HOURS_IN_DAY = 24
MINUTES_IN_HOUR = 60
SECONDS_IN_MINUTE = 60
PCIE_STR = '/sys/bus/pci/drivers/habanalabs/'
OAM_ID_TO_BUS_ID = '3, 0000:34:00.0\n2, 0000:33:00.0\n6, 0000:9a:00.0\n0, 0000:4d:00.0\n7, 0000:9b:00.0\n1, 0000:4e:00.0\n4, 0000:b3:00.0\n5, 0000:b4:00.0\n'

user_args = {}
FILENAME_PREFIX = __file__.replace('.py', '')
INPUT_FILE_PREFIX = ''
hostname = ''

LOGFILE_LOCATION = '/var/log/telegraf/'
LOGFILE_SIZE = 10000000
LOGFILE_NUMBER = 5
logger = logging.getLogger('GaudiMon')

# Stats are collected here before printing in the desired output format
host_dict = {}

###############################################################################
# BEGIN: Generic functions
###############################################################################

def pre_checks_passed(argv):
    """Python version check"""

    if sys.version_info[0] < 3:
        print('Unsupported with Python 2. Must use Python 3')
        logger.error('Unsupported with Python 2. Must use Python 3')
        return False
    if len(argv) <= 1:
        print('Try -h option for usage help')
        return False

    return True


def parse_cmdline_arguments():
    """Parse input arguments"""

    desc_str = \
    'Gather information/stats from Intel Gaudi Servers and print output\n' + \
    'in formats like InfluxDB Line protocol. This file uses Intel\'s\n' + \
    'hl-smi and other OS utilities to get data'

    parser = argparse.ArgumentParser(description=desc_str,
                formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('output_format', action='store', help='specify the \
            output format', choices=['dict', 'influxdb-lp'])
    parser.add_argument('-s', dest='stats', \
            action='store_true', default=False, help='Collect Gaudi card Stats\
            like power usage, utilization, temperature, etc. OK to run this at \
            a fine granularity of 5s')
    parser.add_argument('-m', dest='meta', \
            action='store_true', default=False, help='Collect Gaudi card \
            metadata like serial, model, etc. This information is not \
            expected to change, so run this at 1h or longer')
    parser.add_argument('-iis', dest='int_intf_stats', \
            action='store_true', default=False, help='Collect Gaudi card \
            Internal Interfaces Stats. This collection takes approx 30s so \
            run it at 60s or longer')
    parser.add_argument('-eis', dest='ext_intf_stats', \
            action='store_true', default=False, help='Collect Gaudi card \
            External Interfaces Stats')
    parser.add_argument('-eist', dest='ext_intf_status', \
            action='store_true', default=False, help='Gaudi card \
            External Interfaces Status. No stats.')
    parser.add_argument('-sobm', dest='sobm', \
            action='store_true', default=False, help='Use Static OAM to BUS-id \
             mapping. This option is useful under failure conditions when an \
             OAM-id is N/A. This mapping is not expected to change so using \
             static mapping should work or even better')
    parser.add_argument('-v', dest='verbose', \
            action='store_true', default=False, help='warn and above')
    parser.add_argument('-vv', dest='more_verbose', \
            action='store_true', default=False, help='info and above')
    parser.add_argument('-vvv', dest='most_verbose', \
            action='store_true', default=False, help='debug and above')
    parser.add_argument('-vvvv', dest='raw_dump', \
            action='store_true', default=False, help='Dump raw data')

    args = parser.parse_args()
    user_args['output_format'] = args.output_format
    user_args['stats'] = args.stats
    user_args['meta'] = args.meta
    user_args['int_intf_stats'] = args.int_intf_stats
    user_args['ext_intf_stats'] = args.ext_intf_stats
    user_args['ext_intf_status'] = args.ext_intf_status
    user_args['sobm'] = args.sobm
    user_args['verbose'] = args.verbose
    user_args['more_verbose'] = args.more_verbose
    user_args['most_verbose'] = args.most_verbose
    user_args['raw_dump'] = args.raw_dump

def setup_logging():
    """Setup logging"""

    this_filename = (FILENAME_PREFIX.split('/'))[-1]
    logfile_location = LOGFILE_LOCATION + this_filename
    logfile_prefix = logfile_location + '/' + this_filename
    try:
        os.mkdir(logfile_location)
    except FileExistsError:
        pass
    except Exception:
        # Log in local directory if can't be created in LOGFILE_LOCATION
        logfile_prefix = FILENAME_PREFIX
    finally:
        if user_args['stats']:
            logfile_name = logfile_prefix + '_s.log'
        elif user_args['meta']:
            logfile_name = logfile_prefix + '_m.log'
        elif user_args['int_intf_stats']:
            logfile_name = logfile_prefix + '_iis.log'
        elif user_args['ext_intf_stats'] or user_args['ext_intf_status']:
            logfile_name = logfile_prefix + '_eis.log'
        else:
            logfile_name = logfile_prefix + '.log'

        rotator = RotatingFileHandler(logfile_name, maxBytes=LOGFILE_SIZE,
                                      backupCount=LOGFILE_NUMBER)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        rotator.setFormatter(formatter)
        logger.addHandler(rotator)

        if user_args.get('verbose'):
            logger.setLevel(logging.WARNING)
        if user_args.get('more_verbose'):
            logger.setLevel(logging.INFO)
        if user_args.get('most_verbose') or user_args.get('raw_dump'):
            logger.setLevel(logging.DEBUG)

###############################################################################
# END: Generic functions
###############################################################################

###############################################################################
# BEGIN: Input functions
###############################################################################

def run_cmd(cmd):
    cmd_list = cmd.split(' ')
    ret = None
    # TODO: This ret needs proper handling
    try:
        output = subprocess.run(cmd_list, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        if output.returncode != 0:
            logger.error(cmd + ' failed:' + \
                         str(output.stderr.decode('utf-8').strip()))
        else:
            ret = str(output.stdout.decode('utf-8').strip())
    except Exception as e:
        logger.exception('Exception: %s', e)
    return ret

def get_gaudi_module_id_and_bus_id():
    global hostname
    hostname_cmd = 'cat /etc/hostname'
    result = run_cmd(hostname_cmd)
    if result is None:
        logger.error('Error: ' + hostname_cmd)
        return
    hostname = result
    logger.info('Got hostname: %s', hostname)
    host_dict[hostname] = {}
    host_dict[hostname]['gaudi2'] = {}
    host_dict[hostname]['meta'] = {}
    gaudi_dict = host_dict[hostname]['gaudi2']

    logger.info('Getting oam id  and bus id')

    cmd = 'hl-smi -Q module_id,bus_id -f csv,noheader'
    if user_args['sobm']:
        result = OAM_ID_TO_BUS_ID
    else:
        result = run_cmd(cmd)
    if result is None:
        logger.error('Error: %s', cmd)
        return
    for oam in result.splitlines():
        oam_list = oam.split(',')
        oam_id = oam_list[0]
        oam_bus_id = oam_list[1].strip()
        gaudi_dict[oam_id] = {}
        gaudi_dict[oam_id]['bus_id'] = oam_bus_id
        gaudi_dict[oam_id]['intf_dict'] = {}
        gaudi_dict[oam_id]['intf_dict']['internal'] = {}
        gaudi_dict[oam_id]['intf_dict']['external'] = {}
        gaudi_dict[oam_id]['meta'] = {}
        gaudi_dict[oam_id]['stats'] = {}

def get_gaudi_l_stats():
    gaudi_dict = host_dict[hostname]['gaudi2']
    logger.info('Getting Gaudi stats')
    cmd = 'hl-smi'
    result = run_cmd(cmd)
    if result is None:
        logger.error('Error: ' + cmd)
        return
    sub_result = result[result.find('Compute M'): result.find('Compute Processes')]
    section_list = sub_result.split('-------------------------------')
    for section in section_list:
        bus_id = ''.join(re.findall(r'0000:.*00\.0', section, re.IGNORECASE))
        temperature = ''.join(re.findall(r'(\d+)C', section, re.IGNORECASE))
        util = ''.join(re.findall(r'(\d+)%', section, re.IGNORECASE))
        pwr = ''.join(re.findall(r'(\d+)W /', section, re.IGNORECASE))
        pwr_max = ''.join(re.findall(r'/ (\d+)W \|', section, re.IGNORECASE))
        mem = ''.join(re.findall(r'(\d+)MiB /', section, re.IGNORECASE))
        mem_max = ''.join(re.findall(r'/ (\d+)MiB \|', section, re.IGNORECASE))
        un_ecc = ''.join(re.findall(r'\|[ ]{1,}(\d+)  \|\n\|', section, re.IGNORECASE))

        # Ignore when reported temperature is very large unrealistic number like 505712272
        if temperature != '' and int(temperature) > 300:
            logger.warning('TEMPERATURE out of bound > 300 C for %s', bus_id)
            continue

        for oam_id, oam_attr in gaudi_dict.items():
            if bus_id == oam_attr['bus_id']:
                stats_dict = oam_attr['stats']
                stats_dict['temperature'] = temperature
                stats_dict['util'] = util
                stats_dict['pwr'] = pwr
                stats_dict['pwr_max'] = pwr_max
                stats_dict['mem'] = mem
                stats_dict['mem_max'] = mem_max
                stats_dict['un_ecc'] = un_ecc
                break

def get_gaudi_meta_data():
    gaudi_dict = host_dict[hostname]['gaudi2']
    host_meta_dict = host_dict[hostname]['meta']

    logger.info('Getting metadata')

    os_cmd = 'cat /etc/os-release'
    os_result = run_cmd(os_cmd)
    if os_result is None:
        logger.error('Error: ' + os_cmd)
        return
    host_meta_dict['os_release'] = \
        ''.join(re.findall(r'PRETTY_NAME="(.*)"', os_result, re.IGNORECASE))

    lscpu_cmd = 'lscpu'
    lscpu_result = run_cmd(lscpu_cmd)
    if lscpu_result is None:
        logger.error('Error: ' + lscpu_cmd)
        return
    host_meta_dict['cpu_model'] = \
            ''.join(re.findall(r'Model name:[ ]{1,}(.*)\n', lscpu_result, re.IGNORECASE))

    nproc_cmd = 'nproc'
    nproc_result = run_cmd(nproc_cmd)
    if nproc_result is None:
        logger.error('Error: ' + nproc_cmd)
        return
    host_meta_dict['num_cpu'] = nproc_result

    cmd = 'hl-smi -q'
    result = run_cmd(cmd)
    if result is None:
        logger.error('Error: ' + cmd)
        return
    driver_ver = ''.join(re.findall(r'Driver Version.*: (.*)\n', result, re.IGNORECASE))
    result_list = result.split('] AIP')
    for output in result_list:
        bus_id = ''.join(re.findall(r'Bus Id.*: (.*)\n', output, re.IGNORECASE))
        gaudi_model = ''.join(re.findall(r'Product Name.*: (.*)\n', output, re.IGNORECASE))
        serial = ''.join(re.findall(r'Serial Number.*: (.*)\n', output, re.IGNORECASE))
        status = ''.join(re.findall(r'Module status.*: (.*)\n', output, re.IGNORECASE))
        clock = re.findall(r'] soc.*: (\d+.*) MHz|$', output, re.IGNORECASE)[0]

        for oam_id, oam_attr in gaudi_dict.items():
            if bus_id == oam_attr['bus_id']:
                meta_dict = oam_attr['meta']
                meta_dict['driver_version'] = driver_ver
                meta_dict['gaudi_model'] = gaudi_model
                meta_dict['serial'] = serial
                meta_dict['status'] = status
                meta_dict['clock'] = clock

def get_gaudi_internal_intf_stats():
    gaudi_dict = host_dict[hostname]['gaudi2']

    logger.info('Getting Gaudi internal interface stats')

    for oam_id, oam_attr in gaudi_dict.items():
        bus_id = oam_attr['bus_id']
        ii_dict = oam_attr['intf_dict']['internal']
        # hl-smi -n ports -i 0000:9a:00.0 returns only internal interfaces
        link_cmd = 'hl-smi -n link -i ' + bus_id
        link_result = run_cmd(link_cmd)
        if link_result is None:
            logger.error('Error: ' + link_cmd)
            continue
        # Output format is
        # port 7: UP
        # port 9: UP
        # port 10:        UP
        # port 11:        UP
        for line in link_result.splitlines():
            if ':' in line:
                port, state = line.split(':')
                port = int(''.join(re.findall(r'\d+', port, re.IGNORECASE)))
                ii_dict[port] = {}
                ii_dict[port]['meta'] = {}
                ii_dict[port]['stats'] = {}
                ii_dict[port]['meta']['oper_state'] = state.strip()

        # hl-smi -n stats -i 0000:9a:00.0 returns stats for internal interfaces
        s_cmd = 'hl-smi -n stats -i ' + bus_id
        s_result = run_cmd(s_cmd)
        if s_result is None:
            logger.error('Error: ' + s_cmd)
            continue
        # Output format is
        # port 0:
        #    pcs_local_faults: 0
        #    pcs_remote_faults: 0
        #    ...
        # port 1:
        #    pcs_local_faults: 0
        #    ...
        p_dict = None
        pd_dict = None
        # Skip counters
        # etherStatsOctets and etherStatsPkts are used for Tx and Rx
        # Instead of etherStatsOctets, use OctetsReceivedOK, OctetsTransmittedOK
        # Instead of etherStatsPkts, use aFramesReceivedOK, aFramesTransmittedOK
        # Also skip duplicates for In and Out
        skip = ('etherStatsOctets', 'etherStatsPkts', 'etherStatsPkts64Octets', \
                'etherStatsPkts65to127Octets', 'etherStatsPkts128to255Octets', \
                'etherStatsPkts256to511Octets', 'etherStatsPkts512to1023Octets', \
                'etherStatsPkts1024to1518Octets', 'etherStatsPkts1519toMaxOctets', \
                'etherStatsPkts1519toMaxOctets')
        for line in s_result.splitlines():
            if 'port' in line:
                s_port = int(''.join(re.findall(r'\d+', line, re.IGNORECASE)))
                p_dict = ii_dict[s_port]
                ps_dict = p_dict['stats']
                logger.debug('Bus: %s, Port: %s', bus_id, s_port)
                continue
            if ':' in line:
                k, v = line.split(':')
                # Remove space in counter name e.g.pre_FEC_SER_exp (negative),\
                # Congestion Q err
                k = k.strip().replace(' ', '_').replace('(', '').\
                    replace(')', '')
                if k in skip:
                    logger.debug('Skip %s', k)
                    continue
                v = int(v.strip())
                ps_dict[k] = v

def get_gaudi_external_intf_stats():
    gaudi_dict = host_dict[hostname]['gaudi2']

    logger.info('Getting Gaudi external interface stats')

    for oam_id, oam_attr in gaudi_dict.items():
        bus_id = oam_attr['bus_id']
        ei_dict = oam_attr['intf_dict']['external']
        intf_path = PCIE_STR + oam_attr['bus_id'] + '/net/'
        cmd = 'ls ' + intf_path
        result = run_cmd(cmd)
        if result is None:
            logger.error('Error: ' + cmd)
            continue
        for intf_name in result.splitlines():
            address = 'cat ' + intf_path + intf_name + '/address'
            mac = run_cmd(address)
            if mac is None:
                logger.error('Error: ' + address)
                continue
            ei_dict[mac] = {}
            ei_dict[mac]['meta'] = {}
            ei_dict[mac]['stats'] = {}
            ei_dict[mac]['meta']['intf'] = intf_name

            operstate = 'cat ' + intf_path + intf_name + '/operstate'
            operstate_r = run_cmd(operstate)
            if operstate_r is None:
                logger.error('Error: ' + operstate)
                continue
            ei_dict[mac]['meta']['oper_state'] = operstate_r

            if operstate_r == 'up':
                speed_cmd = 'cat ' + intf_path + intf_name + '/speed'
                speed_r = run_cmd(speed_cmd)
                if speed_r is None:
                    logger.error('Error: ' + speed_cmd)
                    continue
                ei_dict[mac]['meta']['oper_speed'] = speed_r

            # get neighbor info using LLDP
            lldp_cmd = 'sudo lldptool -t -n -i ' + intf_name
            lldp_r = run_cmd(lldp_cmd)
            if lldp_r is None:
                logger.error('Error: ' + lldp_cmd)
            else:
                i = 0
                result_list = lldp_r.splitlines()
                for line in result_list:
                    i = i + 1
                    if 'System Name' in line:
                        # System name is in the next line
                        peer_name = result_list[i].strip()
                        ei_dict[mac]['meta']['peer_name'] = peer_name
                    if 'Port ID TLV' in line:
                        # Port name is in the next line
                        peer_intf = result_list[i].replace('Ifname: ', '').strip()
                        ei_dict[mac]['meta']['peer_intf'] = peer_intf
                    if 'System capabilities' in line and 'ridge' in line:
                        ei_dict[mac]['meta']['peer_type'] = 'switch'
                    if 'Management Address' in line:
                        if 'IPv4' in result_list[i]:
                            peer = result_list[i].replace('IPv4: ', '').strip()
                            ei_dict[mac]['meta']['peer'] = peer

            eis_dict = ei_dict[mac]['stats']

            cdc = 'cat ' + intf_path + intf_name + '/carrier_down_count'
            cdc_r = run_cmd(cdc)
            if cdc_r is None:
                logger.error('Error: ' + cdc)
            else:
                eis_dict['cdc'] = cdc_r

            cuc = 'cat ' + intf_path + intf_name + '/carrier_up_count'
            cuc_r = run_cmd(cuc)
            if cuc_r is None:
                logger.error('Error: ' + cuc)
            else:
                eis_dict['cuc'] = cuc_r

            if user_args['ext_intf_status']:
                logger.debug('Collecting only status. No stats: ' + intf_name)
                continue

            # get ethtool stats
            ethtool_cmd = 'ethtool -S ' + intf_name
            ethtool_r = run_cmd(ethtool_cmd)
            if ethtool_r is None:
                logger.error('Error: ' + ethtool_cmd)
                continue

            # Output is in the following format
            #NIC statistics:
            #     rx_packets: 56529
            #     tx_packets: 38117
            #     rx_bytes: 17685919
            # Skip counters
            # etherStatsOctets and etherStatsPkts are used for Tx and Rx
            # Instead of etherStatsOctets, use OctetsReceivedOK, OctetsTransmittedOK
            # Instead of etherStatsPkts, use aFramesReceivedOK, aFramesTransmittedOK
            # Also skip duplicates for In and Out
            skip = ('etherStatsOctets', 'etherStatsPkts', 'etherStatsPkts64Octets', \
                    'etherStatsPkts65to127Octets', 'etherStatsPkts128to255Octets', \
                    'etherStatsPkts256to511Octets', 'etherStatsPkts512to1023Octets', \
                    'etherStatsPkts1024to1518Octets', 'etherStatsPkts1519toMaxOctets', \
                    'etherStatsPkts1519toMaxOctets')
            for line in ethtool_r.splitlines():
                if 'NIC' in line:
                    continue
                if ':' in line:
                    k, v = line.split(':')
                    # Remove space in counter name e.g.pre_FEC_SER_exp (negative),\
                    # Congestion Q err
                    k = k.strip().replace(' ', '_').replace('(', '').\
                        replace(')', '')
                    if k in skip:
                        logger.debug('Skip %s', k)
                        continue
                    v = int(v.strip())
                    eis_dict[k] = v

###############################################################################
# END: Input functions
###############################################################################

###############################################################################
# BEGIN: Output functions
###############################################################################

def print_output_in_influxdb_lp():
    """
    InfluxDB Line Protocol Reference
        * Never double or single quote the timestamp
        * Never single quote field values
        * Do not double or single quote measurement names, tag keys, tag values,
          and field keys
        * Do not double quote field values that are floats, integers, or Booleans
        * Do double quote field values that are strings
        * Performance tips: sort by tag key
    Example: myMeasurement,tag1=tag1val,tag2=tag2val Field1="testData",Field2=3
    """
    final_print_string = ''
    gaudi_prefix = 'GaudiMon'
    gaudi_ii_prefix = 'GaudiIntIntf'
    gaudi_ei_prefix = 'GaudiExtIntf'
    gaudi_str = ''
    ii_str = ''
    ei_str = ''

    for hostname, host_attr in host_dict.items():
        host_tags = ''
        host_tags = host_tags + ',host=' + hostname
        host_meta_dict = host_attr['meta']
        host_meta_str = ''
        for key, val in host_meta_dict.items():
            # Avoid null tags
            if str(val) == '':
                continue
            if key in ('cpu_model', 'os_release'):
                host_meta_str = host_meta_str + ',' + key + '="' + str(val) + '"'
            else:
                host_meta_str = host_meta_str + ',' + key + '=' + str(val)

        gaudi_dict = host_attr['gaudi2']
        for oam_id, oam_attr in gaudi_dict.items():
            gaudi_fields = ''
            gaudi_tags = ''
            gaudi_tags = gaudi_tags + ',oam_id=' + str(oam_id)
            gaudi_tags = gaudi_tags + ',bus_id=' + str(oam_attr['bus_id'])
            gaudi_meta_dict = oam_attr['meta']
            gaudi_stats_dict = oam_attr['stats']
            for key, val in gaudi_meta_dict.items():
                sep = ' ' if gaudi_fields == '' else ','
                # Avoid null tags
                if str(val) == '':
                    continue
                if key in ('clock'):
                    gaudi_fields = gaudi_fields + sep + key + '=' + str(val)
                else:
                    gaudi_fields = gaudi_fields + sep + key + '="' + str(val) + '"'
            for key, val in gaudi_stats_dict.items():
                sep = ' ' if gaudi_fields == '' else ','
                # Avoid null tags
                if str(val) == '':
                    continue
                gaudi_fields = gaudi_fields + sep + key + '=' + str(val)

            if gaudi_fields != '':
                gaudi_fields = gaudi_fields + host_meta_str + '\n'
                gaudi_str = gaudi_str + gaudi_prefix + host_tags + gaudi_tags + \
                        gaudi_fields

            ii_dict = oam_attr['intf_dict']['internal']
            for port, port_attr in ii_dict.items():
                ii_fields = ''
                ii_tags = ''
                ii_tags = ii_tags + ',bus_id=' + str(oam_attr['bus_id']) + \
                          ',oam_id=' + str(oam_id) + ',intf=' + str(port)
                for key, val in ii_dict[port]['meta'].items():
                    if key in ('oper_state'):
                        ii_tags = ii_tags + ',' + key + '=' + val
                for key, val in ii_dict[port]['stats'].items():
                    sep = ' ' if ii_fields == '' else ','
                    # Avoid null values
                    if str(val) == '':
                        continue
                    ii_fields = ii_fields + sep + key + '=' + str(val)
                ii_fields = ii_fields + '\n'
                ii_str = ii_str + gaudi_ii_prefix + ii_tags + ii_fields

            ei_dict = oam_attr['intf_dict']['external']
            for mac, intf_attr in ei_dict.items():
                ei_fields = ''
                ei_tags = ''
                ei_tags = ei_tags + ',bus_id=' + str(oam_attr['bus_id']) + \
                          ',oam_id=' + str(oam_id)
                for key, val in intf_attr['meta'].items():
                    ei_tags = ei_tags + ',' + key + '=' + val
                for key, val in intf_attr['stats'].items():
                    sep = ' ' if ei_fields == '' else ','
                    # Avoid null values
                    if str(val) == '':
                        continue
                    ei_fields = ei_fields + sep + key + '=' + str(val)
                ei_fields = ei_fields + ',mac="' + mac + '"'
                ei_fields = ei_fields + '\n'
                ei_str = ei_str + gaudi_ei_prefix + ei_tags + ei_fields

    final_print_string = final_print_string + gaudi_str + ii_str + ei_str
    print(final_print_string)

def print_output():
    """Print outout in the desired output format"""

    if user_args['output_format'] == 'dict':
        current_log_level = logger.level
        logger.setLevel(logging.DEBUG)
        logger.info('Printing host_dict')
        logger.debug('\n%s', json.dumps(host_dict, indent=2))
        logger.info('Printing output DONE')
        logger.setLevel(current_log_level)
    if user_args['output_format'] == 'influxdb-lp':
        logger.info('Printing output in InfluxDB Line Protocol format')
        print_output_in_influxdb_lp()
        logger.info('Printing output - DONE')

###############################################################################
# END: Output functions
###############################################################################

def main(argv):
    """The beginning of the beginning"""

    # Initial tasks
    if not pre_checks_passed(argv):
        return
    parse_cmdline_arguments()

    setup_logging()

    logger.warning('---- START (version %s) (last update %s) ----', \
                   __version__, __updated__)

    # Gather data
    get_gaudi_module_id_and_bus_id()
    if user_args['stats']:
        get_gaudi_l_stats()
    if user_args['meta']:
        get_gaudi_meta_data()

    if user_args['int_intf_stats']:
        get_gaudi_internal_intf_stats()

    if user_args['ext_intf_stats'] or user_args['ext_intf_status']:
        get_gaudi_external_intf_stats()

    # Print output
    print_output()

    # Final tasks
    logger.warning('---------- END ----------')

if __name__ == '__main__':
    main(sys.argv)
