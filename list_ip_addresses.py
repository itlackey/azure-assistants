#!/usr/bin/env python3

import json
import subprocess
import pandas as pd

OUTPUT_FILE = "azure_ip_addresses.csv"

def run_az(command: list[str]) -> list[dict]:
    print(f"Running command: {' '.join(['az'] + command)}")
    result = subprocess.run(["az"] + command + ["-o", "json"], capture_output=True, text=True)
    result.check_returncode()
    return json.loads(result.stdout)

def get_vm_ips():
    print("Fetching VM IP addresses...")
    rows = []
    vms = run_az(["vm", "list"])
    for vm in vms:
        name = vm["name"]
        rg = vm["resourceGroup"]
        location = vm["location"]
        nic_ids = run_az(["vm", "show", "-g", rg, "-n", name, "--query", "networkProfile.networkInterfaces[].id"])
        for nic_id in nic_ids:
            nic = run_az(["network", "nic", "show", "--ids", nic_id])
            for config in nic.get("ipConfigurations", []):
                private_ip = config.get("privateIPAddress")
                if private_ip:
                    rows.append(["VM", name, rg, location, private_ip, "Private"])
                pip_id = config.get("publicIPAddress", {}).get("id")
                if pip_id:
                    pip = run_az(["network", "public-ip", "show", "--ids", pip_id])
                    public_ip = pip.get("ipAddress")
                    if public_ip:
                        rows.append(["VM", name, rg, location, public_ip, "Public"])
    return rows

def get_public_ips():
    print("Fetching Public IP addresses...")
    rows = []
    public_ips = run_az(["network", "public-ip", "list"])
    for pip in public_ips:
        ip = pip.get("ipAddress")
        if ip:
            rows.append(["PublicIP", pip["name"], pip["resourceGroup"], pip["location"], ip, "Public"])
    return rows

def get_app_gateway_ips():
    print("Fetching Application Gateway IP addresses...")
    rows = []
    gateways = run_az(["network", "application-gateway", "list"])
    for gw in gateways:
        name, rg, location = gw["name"], gw["resourceGroup"], gw["location"]
        frontends = run_az(["network", "application-gateway", "frontend-ip", "list", "--gateway-name", name, "-g", rg])
        for fe in frontends:
            private_ip = fe.get("privateIPAddress")
            if private_ip:
                rows.append(["AppGateway", name, rg, location, private_ip, "Private"])
            pip_id = fe.get("publicIPAddress", {}).get("id")
            if pip_id:
                pip = run_az(["network", "public-ip", "show", "--ids", pip_id])
                public_ip = pip.get("ipAddress")
                if public_ip:
                    rows.append(["AppGateway", name, rg, location, public_ip, "Public"])
    return rows

def get_private_endpoints():
    print("Fetching Private Endpoint IP addresses...")
    rows = []
    endpoints = run_az(["network", "private-endpoint", "list"])
    for pe in endpoints:
        name, rg, location = pe["name"], pe["resourceGroup"], pe["location"]
        configs = pe.get("ipConfigurations", [])
        for config in configs:
            ip = config.get("privateIPAddress")
            if ip:
                rows.append(["PrivateEndpoint", name, rg, location, ip, "Private"])
    return rows

def get_mysql_ips():
    print("Fetching MySQL Flexible Server IP addresses...")
    rows = []
    mysql_servers = run_az(["mysql", "flexible-server", "list"])
    for server in mysql_servers:
        name, rg, location = server["name"], server["resourceGroup"], server["location"]
        ip = server.get("fullyQualifiedDomainName")
        if ip:
            rows.append(["MySQLFlexibleServer", name, rg, location, ip, "Public"])
    return rows

def get_postgres_ips():
    print("Fetching PostgreSQL Server IP addresses...")
    rows = []
    postgres_servers = run_az(["postgres", "server", "list"])
    for server in postgres_servers:
        name, rg, location = server["name"], server["resourceGroup"], server["location"]
        ip = server.get("fullyQualifiedDomainName")
        if ip:
            rows.append(["PostgreSQLServer", name, rg, location, ip, "Public"])
    return rows

def get_network_interface_ips():
    print("Fetching Network Interface IP addresses...")
    rows = []
    nics = run_az(["network", "nic", "list"])
    for nic in nics:
        name, rg, location = nic["name"], nic["resourceGroup"], nic["location"]
        for config in nic.get("ipConfigurations", []):
            private_ip = config.get("privateIPAddress")
            if private_ip:
                rows.append(["NetworkInterface", name, rg, location, private_ip, "Private"])
            pip_id = config.get("publicIPAddress", {}).get("id")
            if pip_id:
                pip = run_az(["network", "public-ip", "show", "--ids", pip_id])
                public_ip = pip.get("ipAddress")
                if public_ip:
                    rows.append(["NetworkInterface", name, rg, location, public_ip, "Public"])
    return rows

def get_private_dns_records():
    print("Fetching Private DNS Zone records...")
    rows = []
    dns_zones = run_az(["network", "private-dns", "zone", "list"])
    for zone in dns_zones:
        zone_name = zone["name"]
        rg = zone["resourceGroup"]
        records = run_az(["network", "private-dns", "record-set", "list", "--zone-name", zone_name, "-g", rg])
        for record in records:
            record_name = record["name"]
            for a_record in record.get("aRecords", []):
                ip = a_record.get("ipv4Address")
                if ip:
                    rows.append(["PrivateDNSZone", record_name, rg, zone_name, ip, "Private"])
    return rows

def main():
    print("Starting IP address collection...")
    all_rows = (
        get_vm_ips() +
        get_public_ips() +
        get_app_gateway_ips() +
        get_private_endpoints() +
        get_mysql_ips() +
        get_postgres_ips() +
        get_private_dns_records() +
        get_network_interface_ips()
    )

    print("Writing results to CSV...")
    df = pd.DataFrame(all_rows, columns=["ResourceType", "ResourceName", "ResourceGroup", "Location", "IPAddress", "IPType"])
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved {len(df)} records to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()




#az network private-dns zone show --resource-group i2-redcap-main-rg --name privatelink.mysql.database.azure.com
#az network private-dns link vnet show --resource-group i2-redcap-main-rg --zone-name privatelink.mysql.database.azure.com --name kve3vjofq6p4s