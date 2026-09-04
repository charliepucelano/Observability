import asyncio
import sys
sys.path.insert(0, '/app/backend/data')
import test_homelab_diagnostics as hd
import test_homelab_ops_inspector as ho

async def run_tests():
    out = []
    def log(s):
        out.append(s)
        print(s)

    log("==================================================")
    log("=== RUNNING HOMELAB DIAGNOSTICS & OPS TEST SUITE ===")
    log("==================================================")

    t1 = hd.Tools()
    log("\n[1] Testing query_prometheus('up'):")
    res1 = await t1.query_prometheus("up")
    log(res1)

    log("\n[2] Testing get_thermal_snapshot():")
    res2 = await t1.get_thermal_snapshot()
    log(res2)

    log("\n[3] Testing get_container_status():")
    res3 = await t1.get_container_status()
    log(res3[:350] + "\n...")

    log("\n[4] Testing get_slo_report():")
    res4 = await t1.get_slo_report()
    log(res4)

    log("\n[5] Testing query_prometheus_range('aida64_temp_cpu_diode_celsius', range_hours=2):")
    res5 = await t1.query_prometheus_range("aida64_temp_cpu_diode_celsius", range_hours=2)
    log(res5)

    log("\n[6] Testing query_loki_recent_errors('immich', limit=3):")
    res6 = await t1.query_loki_recent_errors("immich", limit=3)
    log(res6)

    log("\n[7] Testing get_endpoint_latency('immich'):")
    res7 = await t1.get_endpoint_latency("immich")
    log(res7)

    log("\n[8] Testing read_prometheus_config() (secrets scrubber):")
    res8 = await t1.read_prometheus_config()
    log(res8[:350] + "\n...")

    t2 = ho.Tools()
    log("\n==================================================")
    log("=== TESTING HOMELAB OPS INSPECTOR ===")
    log("==================================================")

    log("\n[9] Testing check_backup_drive_headroom():")
    res9 = await t2.check_backup_drive_headroom()
    log(res9)

    log("\n[10] Testing get_backup_status():")
    res10 = await t2.get_backup_status()
    log(res10)

    log("\n[11] Testing get_scheduled_tasks_timeline():")
    res11 = await t2.get_scheduled_tasks_timeline()
    log(res11[:400] + "\n...")

    log("\n[12] Testing get_ha_power_and_thermals() (unconfigured valve):")
    res12 = await t2.get_ha_power_and_thermals()
    log(res12)

if __name__ == '__main__':
    asyncio.run(run_tests())
