#!/bin/bash

# Define input file containing station triplets
input_csv="nrcs.fcst_pts.csv"

# Define output directory
output_dir="./obs_data"
mkdir -p "$output_dir"

# Define request parameters
begin_date="1900-10-01"
end_date="2025-09-30"
#end_date="2025-07-30"
element="SRVO"  # Adjusted streamflow volume

# Read stationTriplets from CSV and loop through each station
tail -n +2 "$input_csv" | while IFS=, read -r stationTriplet; do
    # Trim any whitespace
    stationTriplet=$(echo "$stationTriplet" | tr -d '[:space:]')

    # Construct output filename
    output_file="$output_dir/obs_${stationTriplet//:/_}.json"

    # Make the API request
    curl -X 'GET' \
      "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets=${stationTriplet}&elements=${element}&duration=MONTHLY&beginDate=${begin_date}&endDate=${end_date}&periodRef=END&centralTendencyType=NONE&returnFlags=false&returnOriginalValues=false&returnSuspectData=false" \
      -H 'accept: application/json' > "$output_file"

    echo "Downloaded obs data for $stationTriplet -> $output_file"
done

echo "All observations downloaded!"
