This script will create html outputs for weather station data.
Inputs are a list of weather stations (Synoptic STID) 
The Script is hardcoded for region and 48 hour output
Output: is temp and snow graphs and a wind rose for 48 hours with the ability to step through in 4 hour increments.


Change Log
  11 April: added current wind direction to the current conditions line under the graphs
  12 April: Added a NWS Point Forecast link using the latitude and longitude of the weather station from the API
  12 April: Added Skyline 
  
These are run using the following commands. Substitue the proper paths as needed.
     python3 ~/python/scripts/generate_wasatch_dashboard.py --output /home2/vofgesmy/public_html/brackpackblog/Weather/Wasatch-Weather-Stations.html --server-script-path /home2/vofgesmy/python/scripts/generate_wasatch_dashboard.py

     python3 ~/python/scripts/generate_uintas_dashboard.py --output /home2/vofgesmy/public_html/brackpackblog/Weather/Uintas-Weather-Stations.html --server-script-path /home2/vofgesmy/python/scripts/generate_uintas_dashboard.py

     python3 ~/python/scripts/generate_skyline_dashboard.py --output /home2/vofgesmy/public_html/brackpackblog/Weather/Skyline-Weather-Stations.html --server-script-path /home2/vofgesmy/python/scripts/generate_skyline_dashboard.py
