#!/bin/bash

# Define water years
start_year=2025
end_year=2025

# Define states where NRCS issues water supply forecasts
states=("AZ" "CA" "CO" "ID" "MT" "NV" "NM" "OR" "UT" "WA" "WY")

# Loop through each state
for state in "${states[@]}"; do
  echo "Processing state: $state"

  # Create state directory if not exists
  mkdir -p "./tmp/$state"

  # Loop through each water year
  for wy in $(seq $start_year $end_year); do
    # Define start and end dates for each water year
    begin_date="$((wy-1))-10-01"
    end_date="$wy-09-30"

    # Construct the output filename
    output_file="./tmp/$state/nrcs.${state}.WY${wy}.json"

    # Make the API request for SRVO only
    curl -X 'GET' \
      "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/forecasts?stationTriplets=%2A%3A${state}%3AUSGS&elementCodes=SRVO&beginPublicationDate=${begin_date}&endPublicationDate=${end_date}" \
      -H 'accept: application/json' > "$output_file"

    echo "Saved data for $state WY${wy} to ${output_file}"
  done

  echo "Finished processing state: $state"
done

echo "All states processed!"
