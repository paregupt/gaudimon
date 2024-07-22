# Monitor Intel Gaudi Accelerators using Grafana, InfluxDB and Telegraf.

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

