#!/usr/bin/env python3

import json
import subprocess
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

def run_az(command: list[str]) -> list[dict]:
    print(f"Running command: {' '.join(['az'] + command)}")
    result = subprocess.run(["az"] + command + ["-o", "json"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command: {' '.join(['az'] + command)}")
        print(f"Error message: {result.stderr.strip()}")
        return []  # Return an empty list to avoid breaking the script
    return json.loads(result.stdout)

def get_subscriptions():
    print("Fetching subscriptions...")
    subscriptions = run_az(["account", "list", "--query", "[].id"])
    return subscriptions

def get_public_ips_for_subscription(subscription_id):
    print(f"Fetching Public IP addresses for subscription {subscription_id}...")
    rows = []
    public_ips = run_az(["network", "public-ip", "list", "--subscription", subscription_id])
    for pip in public_ips:
        ip = pip.get("ipAddress")
        if ip:
            rows.append(["PublicIP", pip["name"], pip["resourceGroup"], pip["location"], ip, "Public"])
    return rows

def get_virtual_networks_for_subscription(subscription_id):
    print(f"Fetching Virtual Networks for subscription {subscription_id}...")
    rows = []
    virtual_networks = run_az(["network", "vnet", "list", "--subscription", subscription_id])
    for vnet in virtual_networks:
        name = vnet.get("name")
        resource_group = vnet.get("resourceGroup")
        location = vnet.get("location")
        address_space = vnet.get("addressSpace", {}).get("addressPrefixes", [])
        for address_range in address_space:
            rows.append(["VirtualNetwork", name, resource_group, location, address_range, "Private"])
    return rows

def main():
    print("Starting IP resource collection across all subscriptions...")
    subscriptions = get_subscriptions()
    all_rows = []

    with ThreadPoolExecutor() as executor:
        # Fetch public IPs
        public_ip_futures = [executor.submit(get_public_ips_for_subscription, sub) for sub in subscriptions]
        for future in public_ip_futures:
            all_rows.extend(future.result())

        # Fetch virtual networks
        vnet_futures = [executor.submit(get_virtual_networks_for_subscription, sub) for sub in subscriptions]
        for future in vnet_futures:
            all_rows.extend(future.result())

    print("Writing results to CSV...")
    df = pd.DataFrame(all_rows, columns=["ResourceType", "ResourceName", "ResourceGroup", "Location", "IPAddress", "IPType"])
    output_file = "all_subscriptions_resources.csv"
    df.to_csv(output_file, index=False)
    print(f"Saved {len(df)} records to {output_file}")

if __name__ == "__main__":
    main()