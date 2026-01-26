import logging

from infrahub_sdk import InfrahubClient

DEVICE_TYPES = ["EOS"]
VLANS = [
    {
        "name": "Client",
        "vlan_id": 10,
        "status": "active",
        "role": "user",
        "site": "Amsterdam 1",
    },
    {
        "name": "Server",
        "vlan_id": 100,
        "status": "active",
        "role": "server",
        "site": "Rotterdam 1",
    },
]
DROPDOWNS = [
    {
        "kind": "IpamPrefix",
        "attribute": "role",
        "option": "peer",
        "label": "Peering",
        "color": "#ff0000",
    },
    {
        "kind": "IpamPrefix",
        "attribute": "role",
        "option": "office",
        "label": "Office",
        "color": "#ff1111",
    },
    {
        "kind": "DcimInterface",
        "attribute": "role",
        "option": "host",
        "label": "Host",
        "color": "#02f4fc",
    },
    {
        "kind": "DcimInterface",
        "attribute": "role",
        "option": "peer",
        "label": "Peer",
        "color": "#02f4fc",
    },
]

PREFIXES = [
    {
        "name": "Management",
        "role": "management",
        "prefix": "172.16.10.0/24",
        "description": "Management Prefix",
    },
    {
        "name": "Client",
        "role": "office",
        "prefix": "192.168.1.0/24",
        "description": "Client Prefix",
        "vlan": "Client",
    },
    {
        "name": "Server",
        "role": "server",
        "prefix": "192.168.100.0/24",
        "description": "Server Prefix",
        "vlan": "Server",
    },
    {
        "name": "Peer",
        "role": "peer",
        "prefix": "192.168.200.0/30",
        "description": "Peer Prefix",
    },
]


# TODO: eventually we would like to capture that in infrahub in a device template object
INTERFACE_TEMPLATES = {
    "switch_ams01": [
        {
            "name": "Ethernet1",
            "speed": 1000,
            "role": "peer",
            "description": "Connected to peer switch",
            "kind": "InterfacePhysical",
        },
        {
            "name": "Ethernet2",
            "speed": 1000,
            "role": "host",
            "description": "Connected to host",
            "kind": "InterfacePhysical",
            "l2_mode": "access",
            "speed": 1000,
            "vlan": "Client",
        },
    ],
    "switch_rtm01": [
        {
            "name": "Ethernet1",
            "speed": 1000,
            "role": "peer",
            "description": "Connected to peer switch",
            "kind": "InterfacePhysical",
        },
        {
            "name": "Ethernet2",
            "speed": 1000,
            "role": "host",
            "description": "Connected to server",
            "kind": "InterfacePhysical",
            "l2_mode": "access",
            "speed": 1000,
            "vlan": "Server",
        },
    ],
}


LOCATIONS = [
    {
        "name": "Netherlands",
        "shortname": "NL",
        "timezone": "CET",
        "metros": [
            {
                "name": "Amsterdam",
                "shortname": "ams",
                "sites": [
                    {
                        "name": "Amsterdam 1",
                        "shortname": "ams01",
                    },
                ],
            },
            {
                "name": "Rotterfam",
                "shortname": "rtm",
                "sites": [
                    {
                        "name": "Rotterdam 1",
                        "shortname": "rtm01",
                    },
                ],
            },
        ],
    },
]


async def create_org(client: InfrahubClient, log: logging.Logger, branch: str) -> None:
    manufacturer_obj = await client.create(
        kind="OrganizationManufacturer",
        name="Arista",
    )

    await manufacturer_obj.save(allow_upsert=True)

    for type_name in DEVICE_TYPES:
        # here we +1 to not have switch 0
        device_type_obj = await client.create(
            kind="DcimDeviceType", name=type_name, manufacturer=manufacturer_obj
        )

        await device_type_obj.save(allow_upsert=True)


async def create_location(
    client: InfrahubClient, log: logging.Logger, branch: str
) -> None:
    for country in LOCATIONS:
        # Create country
        country_obj = await client.create(
            kind="LocationCountry",
            name=country["name"],
            shortname=country["shortname"],
        )
        await country_obj.save(allow_upsert=True)

        for metro in country["metros"]:
            # Create metro
            metro_obj = await client.create(
                kind="LocationMetro",
                name=metro["name"],
                shortname=metro["shortname"],
                parent=country_obj,
            )
            await metro_obj.save(allow_upsert=True)

            for site in metro["sites"]:
                site_obj = await client.create(
                    kind="LocationSite",
                    name=site["name"],
                    shortname=site["shortname"],
                    parent=metro_obj,
                )
                await site_obj.save(allow_upsert=True)


async def create_vlans(
    client: InfrahubClient, log: logging.Logger, branch: str
) -> None:
    # create domain
    domain = await client.create(kind="IpamL2Domain", name="default")

    await domain.save(allow_upsert=True)

    for vlan in VLANS:
        vlan["location"] = [
            await client.get(kind="LocationSite", name__value=vlan["site"])
        ]
        vlan_node = await client.create(kind="IpamVLAN", **vlan, l2domain=domain)

        await vlan_node.save(allow_upsert=True)


async def create_prefixes(
    client: InfrahubClient, log: logging.Logger, branch: str
) -> None:
    for prefix in PREFIXES:
        vlan = None
        if "vlan" in prefix:
            vlan = await client.get(kind="IpamVLAN", name__value=prefix["vlan"])
        # Create prefix
        prefix_node = await client.create(
            kind="IpamPrefix",
            status="active",
            prefix=prefix["prefix"],
            member_type="address",
            role=prefix["role"],
            description=prefix["description"],
            vlan=vlan,
        )
        await prefix_node.save(allow_upsert=True)

        # Create management ip pool
        prefix_pool = await client.create(
            kind="CoreIPAddressPool",
            name=f"{prefix['name']} IP pool",
            default_prefix_type="IpamIPPrefix",
            default_prefix_length=24,
            default_address_type="IpamIPAddress",
            default_member_type="address",
            ip_namespace="default",
            resources=[prefix_node],
        )
        await prefix_pool.save(allow_upsert=True)

        if prefix["role"] in ["server", "management", "office"]:
            prefix_node.gateway = prefix_pool

        await prefix_node.save(allow_upsert=True)


async def create_interfaces(
    client: InfrahubClient, device_obj, interface_list: list
) -> None:
    # Prepare the batch object for interfaces
    interface_batch = await client.create_batch()

    # Loop over interface templates
    for interface_template in interface_list:
        interface_data: dict = {
            "name": interface_template["name"],
            "device": device_obj,
            "speed": interface_template["speed"],
            "status": "active",
            "role": interface_template["role"],
        }

        # If we have status defined in the template
        if "status" in interface_template:
            interface_data["status"] = interface_template["status"]

        # If we have status defined in the template
        if "l2_mode" in interface_template:
            interface_data["l2_mode"] = interface_template["l2_mode"]

        # If we have description defined in the template
        if "description" in interface_template:
            interface_data["description"] = interface_template["description"]

        # If we have enable defined in the template
        if "enabled" in interface_template:
            interface_data["enabled"] = interface_template["enabled"]

        if "vlan" in interface_template:
            for vlan in VLANS:
                if interface_template.get("vlan") == vlan["name"]:
                    vlan_obj = await client.get(
                        kind="IpamVLAN", name__value=vlan["name"]
                    )
            interface_data["untagged_vlan"] = vlan_obj

        if interface_template["role"] == "peer":
            peer_pool = await client.get(
                name__value="Peer IP pool", kind="CoreIPAddressPool"
            )
            try:
                ip_address = await client.allocate_next_ip_address(
                    resource_pool=peer_pool, prefix_length=30
                )
                interface_data["ip_addresses"] = [ip_address]
            except:
                pass

        # Create interface
        interface_obj = await client.create(
            kind=interface_template["kind"], data=interface_data
        )

        # Add save operation to the batch
        interface_batch.add(
            task=interface_obj.save, node=interface_obj, allow_upsert=True
        )

    # Execute the batch
    async for node, _ in interface_batch.execute():
        pass  # TODO: Improve that part


async def create_devices(
    client: InfrahubClient, log: logging.Logger, branch: str
) -> None:
    # Query related info
    site_list = await client.all("LocationSite")
    management_pool = await client.get(
        name__value="Management IP pool", kind="CoreIPAddressPool"
    )

    for site in site_list:
        for i in range(1, 2):
            # Create switch object
            switch_obj = await client.create(
                kind="DcimDevice",
                name=f"sw0{str(i)}-{site.shortname.value}",
                description="Office Switch",
                status="active",
                role="leaf",
                location=site,
                device_type=["EOS"],
                primary_address=management_pool,
            )

            await switch_obj.save(allow_upsert=True)

            interface_template = INTERFACE_TEMPLATES[f"switch_{site.shortname.value}"]

            await create_interfaces(client, switch_obj, interface_template)


async def create_link(client: InfrahubClient, log: logging.Logger, branch: str) -> None:
    interfaces = await client.filters(kind="InterfacePhysical", role__value="peer")
    connector = await client.create(
        kind="DcimCable",
        connected_endpoints=interfaces,
        status="connected",
        cable_type="cat6",
        label="Peer Link",
    )
    await connector.save(allow_upsert=True)


async def create_dropdowns(
    client: InfrahubClient, log: logging.Logger, branch: str
) -> None:
    for dropdown in DROPDOWNS:
        try:
            t = await client.schema.add_dropdown_option(**dropdown)
        except Exception as e:
            log.error(f"Failed to create dropdown option: {e}")
            pass


async def run(
    client: InfrahubClient, log: logging.Logger, branch: str, **kwargs
) -> None:
    log.info("Generating dropdowns...")
    await create_dropdowns(client=client, branch=branch, log=log)
    log.info("Generate all org related data...")
    await create_org(client=client, branch=branch, log=log)

    log.info("Generate all location related data...")
    await create_location(client=client, branch=branch, log=log)

    log.info("Generate all vlan related data...")
    await create_vlans(client=client, branch=branch, log=log)

    log.info("Generate all prefixes related data...")
    await create_prefixes(client=client, branch=branch, log=log)

    log.info("Generate all device related data...")
    await create_devices(client=client, branch=branch, log=log)

    log.info("Create connection between devices...")
    await create_link(client=client, branch=branch, log=log)
