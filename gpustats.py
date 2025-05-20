import os
import logging
import traceback
import time
import datetime

import sh
import nvitop
from pymongo import MongoClient
from rcfile import rcfile


config = rcfile('gpustat')

mongo_user, mongo_pw, mongo_host, mongo_port, gpustat_machine = [config.get(k, d) for k, d in (('mongo_user', ''), ('mongo_pw', ''), ('mongo_host', 'localhost'), ('mongo_port', '27017'), ('machine_name', ''))]

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "gpustat.log")),
    ],
)


def get_nvidia_stats():
    free_gpus = set()
    entries = []
    gpu_infos = []

    devices = nvitop.Device.all()
    for device in devices:
        gid = device.index
        gpu_util = device.gpu_utilization()
        gpu_info = {
            "name": device.name(),
            "temperature": device.temperature(),
            "memory_total": device.memory_total(),
            "memory_used": device.memory_used(),
            "utilization": gpu_util,
            "power": device.power_usage() / 1000,
            "users": [],
        }
        processes = device.processes()
        if len(processes) > 0:
            procs = nvitop.GpuProcess.take_snapshots(processes.values(), failsafe=True)
            for proc in procs:
                entries.append(dict(gid=gid, pid=proc.pid, uid=proc.username, perc=gpu_util))
                gpu_info["users"].append(proc.username)
        else:
            free_gpus.add(gid)
        gpu_infos.append(gpu_info)

    free_gpus = sorted(free_gpus)

    return free_gpus, entries, gpu_infos


def get_top_stats():
    nproc = int(sh.nproc("--all"))
    ctext = [l for l in sh.free().split("\n") if l.startswith("Mem:")][0]
    tkns = [t for t in ctext.split() if len(t)]
    mem_total, mem_used = map(int, tkns[1:3])

    try:
        ctext = sh.df("-l")
    except sh.ErrorReturnCode_1 as e:
        if "Key has expired" in e.stderr.decode():
            ctext = e.stdout.decode()
        else:
            raise
    ctext = [l for l in ctext.split("\n") if "system-local" in l][0]
    tkns = [t for t in ctext.split() if len(t)]
    hdd_used, hdd_avail = map(int, tkns[2:4])

    ctext = sh.top("-b", "-n1").split("\n")
    lavg = float(ctext[0].split("load average:")[1].strip().split()[0][:-1])
    ctext = ctext[7:]
    procs = []
    for line in ctext:
        line = [t for t in line.split() if len(t)]
        if len(line) != 12:
            continue
        pid, uid, cpu, mem, cmd = (
            line[0],
            line[1],
            float(line[8]),
            float(line[9]),
            line[11],
        )
        if cpu < 50 and mem < 5:
            continue
        procs.append(dict(pid=pid, uid=uid, cpu=cpu, mem=mem, cmd=cmd))
    return nproc, lavg, mem_total, mem_used, hdd_avail, hdd_used, procs


with MongoClient(
    host=mongo_host,
    port=int(mongo_port),
    username=mongo_user,
    password=mongo_pw,
    authSource="admin",
) as client:
    db = client["gpustat"]
    
    logger.info("Starting gpustat")
    while True:
        logger.info("Updating gpustat...")
        try:
            timestamp = datetime.datetime.now(datetime.timezone.utc)
            free_gpus, entries, gpu_info = get_nvidia_stats()
            db.gpu.insert_one(
                {
                    "timestamp": timestamp,
                    "machine": gpustat_machine,
                    "totalfree": len(free_gpus),
                    "whichfree": free_gpus,
                    "details": entries,
                }
            )
            (
                nproc,
                lavg,
                mem_total,
                mem_used,
                hdd_avail,
                hdd_used,
                procs,
            ) = get_top_stats()
            logger.info(f"Updated {gpustat_machine} gpu stats")

            db.cpu.insert_one(
                {
                    "timestamp": timestamp,
                    "machine": gpustat_machine,
                    "nproc": nproc,
                    "load_avg": lavg,
                    "mem_total": mem_total,
                    "mem_used": mem_used,
                    "hdd_avail": hdd_avail,
                    "hdd_used": hdd_used,
                    "procs": procs,
                }
            )
            db.machines.replace_one(
                {"_id": gpustat_machine}, {"_id": gpustat_machine}, upsert=True
            )
            logger.info(f"Updated {gpustat_machine} cpu stats")

            machine_log = {
                "machineId": gpustat_machine,
                "name": gpustat_machine,
                "timestamp": datetime.datetime(),
                "gpus": gpu_info,
                "cpu": {
                    "nproc": nproc,
                    "load_avg": lavg,
                    "memory_used": mem_used,
                    "memory_total": mem_total,
                    "storage_used": hdd_used,
                    "storage_total": hdd_avail,
                    "procs": procs,
                },
            }
            db.machine_logs.insert_one(machine_log)

            logger.info(f"Updated {gpustat_machine} stats")
        except Exception as e:
            logger.warning(e)
            traceback.print_exc()
        except sh.ErrorReturnCode_1 as e:
            logger.warning(e)
        logger.info("Sleeping for 60 seconds...")
        time.sleep(60)
