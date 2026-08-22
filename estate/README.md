# Open-Source Monitoring Estate

## Startup Order
1. `docker-compose up -d zabbix-db valkey`
2. Wait 15s.
3. `docker-compose up -d zabbix-server zabbix-web`
4. Wait 15s.
5. `docker-compose up -d` (rest of the services)

## RAM Footprint
Estimated footprint for the subset is ~2 - 2.5GB.

## Gate A Cascade
The scenario demonstrates cross-tool correlation by targeting a shared volume:
1. Run `./chaos/fill_disk.sh` which fills the `valkey-data` volume.
2. `node-exporter` detects high disk usage, triggering the `HighDiskUsage` Prometheus alert.
3. Simultaneously, the `zabbix-agent` detects the same usage on the shared mount, triggering a Zabbix filesystem alert.
4. `valkey` (datastore) becomes unresponsive/fails due to no disk space.
5. `cart` service fails to write to valkey, escalating to a failure.
6. `checkout` service throws 5xx errors trying to reach cart.
7. `frontend` error rate spikes as it receives errors from checkout.
8. `blackbox-exporter` synthetic probes fail, triggering `FrontendDown`.

## Teardown
`docker-compose down -v`
