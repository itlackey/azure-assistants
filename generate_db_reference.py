#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path


def run_az(cmd):
    """Run an az CLI command and parse its JSON output."""
    full_cmd = ["az"] + cmd + ["-o", "json"]
    print(f"Running command: {' '.join(full_cmd)}")
    proc = subprocess.run(full_cmd, capture_output=True, text=True)
    proc.check_returncode()
    return json.loads(proc.stdout)

def get_subscription():
    acct = run_az(["account", "show"])
    return {"id": acct.get("id"), "name": acct.get("name")}

def get_server_info(server, rg, kind):
    """Fetch core server properties and tags."""
    if kind == "sql":
        srv = run_az(["sql", "server", "show", "-n", server, "-g", rg])
        fqdn = srv["fullyQualifiedDomainName"]
        admin = srv.get("administratorLogin")
    elif kind == "postgres":
        srv = run_az(["postgres", "flexible-server", "show", "-n", server, "-g", rg])
        fqdn = srv["fullyQualifiedDomainName"]
        admin = srv.get("administratorLogin")
    elif kind == "mysql":
        srv = run_az(["mysql", "flexible-server", "show", "-n", server, "-g", rg])
        fqdn = srv["fullyQualifiedDomainName"]
        admin = srv.get("administratorLogin")
    else:
        raise ValueError(f"Unsupported server type: {kind}")

    tags = srv.get("tags") or {}
    return {
        "serverName": fqdn,
        "resourceGroup": rg,
        "subscription": get_subscription(),
        "region": srv["location"],
        "environment": tags.get("environment"),
        "deploymentDate": tags.get("deploymentDate"),
        "owner": tags.get("owner"),
        "purpose": tags.get("purpose"),
        "dependencies": tags.get("dependencies", "").split(",") if tags.get("dependencies") else [],
        "administratorLogin": admin
    }

def list_databases(server, rg, kind):
    """List databases and their metadata tags."""
    if kind == "sql":
        dbs = run_az(["sql", "db", "list", "-g", rg, "--server", server])
    elif kind == "postgres":
        dbs = run_az(["postgres", "flexible-server", "db", "list", "-n", server, "-g", rg])
    elif kind == "mysql":
        dbs = run_az(["mysql", "flexible-server", "db", "list", "-s", server, "-g", rg])
    else:
        return []

    out = []
    for db in dbs:
        t = db.get("tags") or {}
        entry = {
            "name": db["name"],
            "purpose": t.get("purpose"),
            "impact": t.get("impact"),
            "sensitivity": t.get("sensitivity")
        }
        if kind == "sql":
            entry.update({
                "sku": db.get("sku", {}).get("name"),
                "sizeGB": db.get("maxSizeBytes", 0) // (1024**3)
            })
        out.append(entry)
    return out

def list_firewall_rules(server, rg, kind):
    try:
        if kind == "sql":
            rules = run_az(["sql", "server", "firewall-rule", "list", "-g", rg, "--server", server])
        elif kind == "postgres":
            rules = run_az(["postgres", "flexible-server", "firewall-rule", "list", "-n", server, "-g", rg])
        elif kind == "mysql":
            rules = run_az(["mysql", "flexible-server", "firewall-rule", "list", "-n", server, "-g", rg])
        else:
            return []
        return [
            {"name": r["name"], "startIp": r["startIpAddress"], "endIp": r["endIpAddress"]}
            for r in rules
        ]
    except Exception as e:
        print(f"Error listing firewall rules: {e}")
        return []

def list_vnet_rules(server, rg, kind):
    # only SQL supports explicit vnet-rule CLI
    if kind == "sql":
        vr = run_az(["sql", "server", "vnet-rule", "list", "-g", rg, "--server", server])
        return [{"name": v["name"], "vnetSubnetId": v["virtualNetworkSubnetId"]} for v in vr]
    return []

def list_private_endpoints_og(server, rg, kind):
    if kind == "sql":
        cmd = ["sql", "server", "private-endpoint-connection", "list", "-g", rg, "--server", server]
    elif kind == "postgres":
        cmd = ["postgres", "flexible-server", "private-endpoint-connection", "list", "-g", rg, "-n", server]
    elif kind == "mysql":
        cmd = ["mysql", "flexible-server", "private-endpoint-connection", "list", "-g", rg, "-n", server]
    else:
        return []

    conns = run_az(cmd)
    out = []
    for c in conns:
        pe = c.get("privateEndpoint", {})
        pe_id = pe.get("id")
        if not pe_id:
            continue
        details = run_az(["network", "private-endpoint", "show", "--ids", pe_id])
        cfg = details.get("ipConfigurations", [{}])[0]
        out.append({
            "name": c["name"],
            "status": c.get("privateLinkServiceConnectionState", {}).get("status"),
            "privateLinkResource": details.get("customDnsConfigs", [{}])[0].get("fqdn"),
            "vnetSubnet": cfg.get("subnet", {}).get("id"),
            "privateIP": cfg.get("privateIPAddress")
        })
    return out

def list_private_endpoints(server, rg, kind):
    """
    List all private endpoint connections for:
      - SQL Server (Microsoft.Sql/servers)
      - PostgreSQL Flexible Server (Microsoft.DBforPostgreSQL/flexibleServers)
      - MySQL Flexible Server (Microsoft.DBforMySQL/flexibleServers)
    """
    # choose the Azure resource type
    if kind == "sql":
        resource_type = "Microsoft.Sql/servers"
    elif kind == "postgres":
        resource_type = "Microsoft.DBforPostgreSQL/flexibleServers"
    elif kind == "mysql":
        resource_type = "Microsoft.DBforMySQL/flexibleServers"
    else:
        return []

    # generic list command :contentReference[oaicite:0]{index=0}
    conns = run_az([
        "network", "private-endpoint-connection", "list",
        "--resource-group", rg,
        "--name", server,
        "--type", resource_type
    ])

    rows = []
    for c in conns:
        props = c.get("properties", {})
        status = props.get("privateLinkServiceConnectionState", {})\
                      .get("status")
        pe_id  = props.get("privateEndpoint", {}).get("id")
        if not pe_id:
            continue

        # fetch the actual endpoint NIC to grab the IP & subnet :contentReference[oaicite:1]{index=1}
        pe = run_az(["network", "private-endpoint", "show", "--ids", pe_id])
        cfg = pe.get("ipConfigurations", [{}])[0]
        dns = pe.get("customDnsConfigs", [{}])[0].get("fqdn")

        rows.append({
            "name":                c.get("name"),
            "status":              status,
            "privateLinkResource": dns,
            "vnetSubnet":          cfg.get("subnet", {}).get("id"),
            "privateIP":           cfg.get("privateIPAddress")
        })

    return rows

def main():
    import argparse
    p = argparse.ArgumentParser(description="Generate DB‑Server Reference for SQL/Postgres/MySQL Flexible")
    p.add_argument("-t", "--type", choices=["sql","postgres","mysql"], required=True,
                   help="Server type: sql, postgres, or mysql")
    p.add_argument("-s", "--server", required=True,
                   help="Server name (without .database.windows.net)")
    p.add_argument("-g", "--resource-group", required=True)
    p.add_argument("-o", "--output", help="Output JSON file")
    args = p.parse_args()

    kind = args.type
    server = args.server
    rg = args.resource_group
    out_file = Path(args.output or f"{server}_{kind}_reference.json")

    data = {
        "generalInformation": get_server_info(server, rg, kind),
        "databases": list_databases(server, rg, kind),
        "networking": {
            "firewallRules": list_firewall_rules(server, rg, kind),
            "vnetRules": list_vnet_rules(server, rg, kind),
            "privateEndpoints": list_private_endpoints(server, rg, kind)
        },
        "authentication": {
            "administratorLogin": get_server_info(server, rg, kind)["administratorLogin"]
        },
        # placeholders for manual or extended sections
        "keyVault": None,
        "security": {},
        "performance": {},
        "backupRestore": {},
        "monitoring": {},
        "maintenance": {},
        "disasterRecovery": {},
        "changeManagement": {},
        "knownIssues": [],
        "contactSupport": {}
    }

    with out_file.open("w") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {kind} server reference to {out_file}")

if __name__ == "__main__":
    main()
