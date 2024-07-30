# Monitor Intel Gaudi Accelerators using Grafana, InfluxDB and Telegraf.
The exec input plugin in telegraf runs the collector, gaudi_mon.py and sends the data to the output plugin, influxdb. Grafana reads from influxdb to serve the following and many more use cases.
## Use Cases
31 hosts in a training cluster, each host with eight Gaudi accelerators (OAMs). All 248 OAMs in good health (shown in green).
<img width="1716" alt="image" src="https://github.com/user-attachments/assets/d83de828-1192-4168-ae75-8f46b608e49e">

Compare to a condition when training failed because one OAM is lost. Find this issue quickly as shown by '247' #OAM in red. Also find the host that lost the card from the table showing 'gaudi-2-33' on the top with only 7 OAMs
<img width="1713" alt="Screenshot 2024-07-18 at 9 21 57 AM" src="https://github.com/user-attachments/assets/71b5bbac-e121-4428-88a0-26514c45e26e">

Another instance when 1 out of 256 OAM went to a Disabled state (different from being lost).
<img width="1428" alt="image" src="https://github.com/user-attachments/assets/cbb89cfa-4f73-40d3-8975-91c5adaa3d6f">

Training job kept failing after running for a few mins. No obvious reason was found. But one OAM (connected to bus 9b on host gaudi-2-14) kept reporting excessive power usage (1900 W) even more than the cap (600 W). This spike happened exactly when the training started. Replacing this card made the training complete successfully. 
The tiles in the heatmap are click-able to focus the dashboard only to that specific host.

<img width="357" alt="image" src="https://github.com/user-attachments/assets/e704f662-27c8-44db-b5bf-4d48ae4004b6">

After focusing the dashboard to a specific host, expand "OAM Statistics" to find more details.
<img width="1713" alt="image" src="https://github.com/user-attachments/assets/924daee9-a81f-4aa1-a111-9c92d2439c62">

Details of a host when training starts.
<img width="1714" alt="image" src="https://github.com/user-attachments/assets/c268698a-3ca9-4b46-8803-2af5f52a9eb7">

Heatmap of all the OAMs for their temperature, ECC, Memory usage, Utilization, and Power usage as training completes. Best practice to wait for all the tiles to turn green before starting the next job because sometimes an OAM takes longer to free up from the earlier job.

![ezgif-1-2f7e6b0cbd](https://github.com/user-attachments/assets/b8fc4d1f-3d65-47af-9677-ab977a328d94)

Stats reported by ethtools for Gaudi internal interfaces during training or HCCL benchmark. In addition to utilization (bytes_rx and bytes_tx), these charts report spmu_req_out_of_range_psn, spmu_req_unset_psn, spmu_res_duplicate_psn, and spmu_res_out_of_sequence_psn, CRC, corrected words, uncorrected words, etc. 

<img width="1715" alt="image" src="https://github.com/user-attachments/assets/f679e577-399e-49eb-8f8e-c2cc8960eff0">

Stats reported by ethtools for Gaudi external interfaces during training or HCCL benchmark. The gaudimon collector stitches the output with the connected switchport using LLDP. The output is similar to as shown for Gaudi internal interfaces, but this traffic leaves a server to scale-out training.
<img width="1707" alt="image" src="https://github.com/user-attachments/assets/fc0ada8c-b6c7-4878-baa8-cf42ace34cb4">

<img width="1708" alt="image" src="https://github.com/user-attachments/assets/afde1dc5-0e3b-46ae-9564-2433080cbf30">
<img width="1712" alt="image" src="https://github.com/user-attachments/assets/b753a49b-3ad1-4152-8ba8-23f175b8ea8c">
<img width="1711" alt="image" src="https://github.com/user-attachments/assets/04473f36-c28c-4233-b86c-706c3022a05c">
<img width="1708" alt="image" src="https://github.com/user-attachments/assets/89c2eef2-b471-494d-acd0-f23c57e37a11">
<img width="1712" alt="image" src="https://github.com/user-attachments/assets/ed71e330-ed1d-4dc6-a7d9-fae47faea1dc">

## Installation
A typical environment would have many HLS-Gaudi2 servers (e.g. 32) and one monitoring/management server. Install telegraf on all the (32) HLS-Gaudi2 servers and use its exec input plugin to run the collector, gaudi_mon.py. Telegraf then sends the metrics to the same InfluxDB running on the monitoring/management server. Grafana also runs on the monitoring/management server.

Ubuntun packages are available in this project.

### Telegraf
Install telegraf on all the HLS2-Gaudi2 servers.
Tested version: 1.29.5
```
sudo dpkg -i telegraf_1.29.5-1_amd64.deb
```
Create /usr/local/telegraf director and copy gaudi_mon.py inside it.

The following is the telegraf.conf config
```
  logfile = "/var/log/telegraf/telegraf.log"
  logfile_rotation_max_size = "10MB"
  logfile_rotation_max_archives = 5

[[inputs.exec]]
   interval = "5s"
   commands = [
       "python3 /usr/local/telegraf/gaudi_mon.py -s -sobm -vv influxdb-lp",
   ]
   #timeout = "9s"
   data_format = "influx"

[[inputs.exec]]
   interval = "60s"
   commands = [
       "python3 /usr/local/telegraf/gaudi_mon.py -m -sobm -vv influxdb-lp",
   ]
   timeout = "10s"
   data_format = "influx"

[[inputs.exec]]
   interval = "60s"
   commands = [
       "python3 /usr/local/telegraf/gaudi_mon.py -iis -sobm -vv influxdb-lp",
   ]
   timeout = "59s"
   data_format = "influx"

[[inputs.exec]]
   interval = "10s"
   commands = [
       "python3 /usr/local/telegraf/gaudi_mon.py -eist -sobm -vv influxdb-lp",
   ]
   data_format = "influx"

#[[inputs.exec]]
#   interval = "60s"
#   commands = [
#       "python3 /usr/local/telegraf/gaudi_mon.py -eis -sobm -vv influxdb-lp",
#   ]
#   timeout = "59s"
#   data_format = "influx"

 [[outputs.influxdb]]
    urls = ["http://<ip>:8086"]
    database = "telegraf"
```

## Notes
1. This project uses InfluxDB 1.x.
2. This project has run successfully for a few months monitoring Intel Gaudi 2 accelerators.
