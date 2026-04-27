This script will create html outputs for weather station data.
Inputs are a list of weather stations (Synoptic STID) 
The Script is hardcoded for region and 48 hour output
Output: is temp and snow graphs and a wind rose for 48 hours with the ability to step through in 4 hour increments.


Change Log
* 11 April: added current wind direction to the current conditions line under the graphs
* 12 April: Added a NWS Point Forecast link using the latitude and longitude of the weather station from the API
* 12 April: Added Skyline 
  
These are run using the following commands. Substitute the proper paths as needed.
     python3 ~/python/scripts/generate_wasatch_dashboard.py --output /home2/vofgesmy/public_html/brackpackblog/Weather/Wasatch-Weather-Stations.html --server-script-path /home2/vofgesmy/python/scripts/generate_wasatch_dashboard.py

     python3 ~/python/scripts/generate_uintas_dashboard.py --output /home2/vofgesmy/public_html/brackpackblog/Weather/Uintas-Weather-Stations.html --server-script-path /home2/vofgesmy/python/scripts/generate_uintas_dashboard.py

     python3 ~/python/scripts/generate_skyline_dashboard.py --output /home2/vofgesmy/public_html/brackpackblog/Weather/Skyline-Weather-Stations.html --server-script-path /home2/vofgesmy/python/scripts/generate_skyline_dashboard.py

19 April 2026 updates
* Created a 7-day weather table using the same type of script with input stations as the graphs
* These are run using the following commands. Substitute the proper paths as needed.
    
    0 5,17 * * * python3 python/scripts/generate_skyline_7day_table.py --output /home2/vofgesmy/public_html/brackpackblog/Weather/Skyline-7Day-Table.html --server-script-path /home2/vofgesmy/python/scripts/generate_skyline_7day_table.py --python-path $(which python3)

    0 6,18 * * * python3 python/scripts/generate_wasatch_7day_table.py --output /home2/vofgesmy/public_html/brackpackblog/Weather/Wasatch-7Day-Table.html --server-script-path /home2/vofgesmy/python/scripts/generate_wasatch_7day_table.py --python-path $(which python3)

    0 6,18 * * * python3 python/scripts/generate_uintas_7day_table.py --output /home2/vofgesmy/public_html/brackpackblog/Weather/Uintas-7Day-Table.html --server-script-path /home2/vofgesmy/python/scripts/generate_uintas_7day_table.py --python-path $(which python3)

23 April 2026
Tag pre-changes-2026-04-23 was created to roll back to this point later:                    
  git checkout pre-changes-2026-04-23                                                                                             
  Or to reset your main branch to it:                                                                                             
      git checkout main                                                                                                               
      git reset --hard pre-changes-2026-04-23                                                                                         
      git push --force origin main              

Added precipitation to all of the graphs and tables
added 2 hour tick marks to graphs


24 April 2026
* added the custom weather html page with Brett

27 April 2026
* Precip and Snow Total for 48 hours was incorrect. It was reporting season. This was fixed.
* fixed the 48h snowfall total to match precip total
