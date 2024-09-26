# Monitor Intel Gaudi Accelerators using Grafana, InfluxDB and Telegraf.
The exec input plugin in telegraf runs the collector, gaudi_mon.py and sends the data to the output plugin, influxdb. Grafana reads from influxdb to serve the following and many more use cases.
## Use Cases
31 hosts in a training cluster, each host with eight Gaudi accelerators (OAMs). All 248 OAMs in good health (shown in green).
<img width="1716" alt="image" src="https://github.com/user-attachments/assets/d83de828-1192-4168-ae75-8f46b608e49e">

Compare to a condition when training failed because one OAM is lost. Find this issue quickly as shown by '247' #OAM in red. Also find the host that lost the card from the table showing 'gaudi-2-33' on the top with only 7 OAMs
<img width="1713" alt="Screenshot 2024-07-18 at 9 21 57 AM" src="https://github.com/user-attachments/assets/71b5bbac-e121-4428-88a0-26514c45e26e">

Another instance when 1 out of 256 OAM went to a Disabled state (different from being lost).
<img width="1428" alt="image" src="https://github.com/user-attachments/assets/cbb89cfa-4f73-40d3-8975-91c5adaa3d6f">

Training job kept failing after running for a few mins. No obvious reason was found. But one OAM (connected to bus 9b on host gaudi-2-14) kept reporting excessive power usage (1900 W)  more than the cap (600 W). This spike happened exactly when the training started. Replacing this card made the training complete successfully. 
The tiles in the heatmap are click-able to focus the dashboard only to that specific host.

<img width="357" alt="image" src="https://github.com/user-attachments/assets/e704f662-27c8-44db-b5bf-4d48ae4004b6">

After focusing the dashboard to a specific host, expand "OAM Statistics" to find more details.
<img width="1713" alt="image" src="https://github.com/user-attachments/assets/924daee9-a81f-4aa1-a111-9c92d2439c62">

Details of a host when training starts.
<img width="1714" alt="image" src="https://github.com/user-attachments/assets/c268698a-3ca9-4b46-8803-2af5f52a9eb7">

Heatmap of all the OAMs for their temperature, ECC, Memory usage, Utilization, and Power usage as training completes. Best practice to wait for all the tiles to turn green before starting the next job because sometimes an OAM takes longer to free up from the earlier job.

![ezgif-1-2f7e6b0cbd](https://github.com/user-attachments/assets/b8fc4d1f-3d65-47af-9677-ab977a328d94)

Gaudi external interface states, when and how long the links were down
<img width="1713" alt="image" src="https://github.com/user-attachments/assets/38ae041c-acf3-4c3c-8d52-c0511cc2816b">

Stats reported by ethtools for Gaudi internal interfaces during training or HCCL benchmark. In addition to utilization (bytes_rx and bytes_tx), these charts report spmu_req_out_of_range_psn, spmu_req_unset_psn, spmu_res_duplicate_psn, and spmu_res_out_of_sequence_psn, CRC, corrected words, uncorrected words, etc. 

<img width="1715" alt="image" src="https://github.com/user-attachments/assets/f679e577-399e-49eb-8f8e-c2cc8960eff0">

Stats reported by ethtools for Gaudi external interfaces during training or HCCL benchmark. The gaudimon collector stitches the output with the connected switchport using LLDP. The output is similar to as shown for Gaudi internal interfaces, but this traffic leaves a server to scale-out training.
<img width="1707" alt="image" src="https://github.com/user-attachments/assets/fc0ada8c-b6c7-4878-baa8-cf42ace34cb4">

These detailed graphs explain obscure problems. For example, these graphs show that cw_uncorrect_accum counters are highest on enp179s0d8 and enp77s0d23. These Linux interfaces connect to switchports Eth1/2/1 on switch SW-L1-H-12 and Eth1/1/1 on switch SW-L5-F-08 respectively. These transceivers and cables need verification for excessive bit errors. Also note that the aFrameCheckSequenceErrors (CRC) are reported on the same interfaces during the same time. CRC packets are dropped, explaining the rise in spmu_req_out_of_range_psn, spmu_req_unset_psn, spmu_res_duplicate_psn, and spmu_res_out_of_sequence_psn counters.

<img width="1715" alt="image" src="https://github.com/user-attachments/assets/e5dcadf3-3cc2-4f45-8c55-e79aac86d158">

<img width="1715" alt="image" src="https://github.com/user-attachments/assets/8de606ff-69a4-428b-93e5-9ea1509cbcc0">

<img width="1704" alt="image" src="https://github.com/user-attachments/assets/90531c29-bb3a-4912-b1b1-bbe1108db1fa">

<img width="1704" alt="image" src="https://github.com/user-attachments/assets/43053e6e-7631-4ff1-a729-2a91f9ee2178">

<img width="1711" alt="image" src="https://github.com/user-attachments/assets/dc41681a-196f-4464-8a5d-9e2aa7da6107">


## Installation
A typical environment would have many HLS-Gaudi2 servers (e.g. 32) and one monitoring/management server. Install telegraf on all the (32) HLS-Gaudi2 servers and use its exec input plugin to run the collector, gaudi_mon.py. Telegraf then sends the metrics to the same InfluxDB running on the monitoring/management server. Grafana also runs on the monitoring/management server.

### Telegraf
Install telegraf on all the HLS2-Gaudi2 servers.
Used version: 1.29.5. But any other telegraf version should work.
```
wget https://dl.influxdata.com/telegraf/releases/telegraf_1.29.5-1_amd64.deb 
sudo dpkg -i telegraf_1.29.5-1_amd64.deb
```

Telegraf by default runs as a service by telegraf user. But I prefer running telegraf under a different user with access to sudo command, such as sudo lldptool command that gaudimon uses. So edit /lib/systemd/system/telegraf.service and change User=telegraf to something else, for example User=ciscouser.

To allow running sudo command by ciscouser without asking for password, I add a new file, name 91-ciscouser at /etc/sudoers.d/ with the following line

```
ciscouser ALL=(ALL) NOPASSWD:ALL
```
Change this content to allow only specific sudo commands without asking for password.

Change ownership of /var/log/telegraf to ciscouser to allow this user to write logs
```
sudo chown -R ciscouser:sudo /var/log/telegraf
```

Create /usr/local/telegraf director and copy gaudi_mon.py inside it.
```
sudo mkdir /usr/local/telegraf
sudo chown ciscouser:sudo /usr/local/telegraf
mv gaudi_mon.py /usr/local/telegraf/
```
sudo cp telegraf.service /lib/systemd/system/telegraf.service

Finally, restart telegraf service
```
sudo systemctl daemon-reload
sudo systemctl start telegraf
```

The following is the telegraf.conf config. Change/Edit this in /etc/telegraf/telegraf.conf

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

[[inputs.exec]]
   interval = "60s"
   commands = [
       "python3 /usr/local/telegraf/gaudi_mon.py -eis -sobm -vv influxdb-lp",
   ]
   timeout = "59s"
   data_format = "influx"

 [[outputs.influxdb]]
    urls = ["http://<ip>:8086"]
    database = "telegraf"
```

All these steps need to be done on all the HLS-Gaudi2 servers. Do the above steps on one server and verify it works. Then copy the files from this server to all the servers using the following 

```
for i in {11..42}; do (ssh gaudi-2-$i 'scp -r 172.22.36.80:~/gaudimon ~/ ; sudo dpkg -i ~/gaudimon/telegraf_1.29.5-1_amd64.deb ; sudo cp ~/gaudimon/telegraf.service /lib/systemd/system/telegraf.service ; sudo cp ~/gaudimon/telegraf.conf /etc/telegraf/telegraf.conf ; sudo chown -R ciscouser:sudo /var/log/telegraf ; sudo mkdir /usr/local/telegraf ; sudo chown ciscouser:sudo /usr/local/telegraf ; cp ~/gaudimon/gaudi_mon.py /usr/local/telegraf/ ;  sudo systemctl daemon-reload ; sudo systemctl start telegraf '); done
```

## Notes
1. This project uses InfluxDB 1.x.
2. This project has run successfully for a few months monitoring Intel Gaudi 2 accelerators.
