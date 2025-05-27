import os
import logging
import re
import traceback
import time
import datetime

import sh
import nvitop
from pymongo import MongoClient
from rcfile import rcfile


config = rcfile('gpustat')


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
    gpu_infos = []
    devices = nvitop.Device.all()
    for device in devices:
        gid = device.index
        gpu_util = device.gpu_utilization()
        gpu_info = {
            "idx": gid,
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
                gpu_info["users"].append(proc.username)
        gpu_infos.append(gpu_info)

    return gpu_infos


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
    lines = [line.split() for line in ctext.split("\n") if len(line.strip())]
    path_to_sizes = {line[-1].strip(): (line[2], line[3]) for line in lines}
    if "/local" in path_to_sizes:
        sizes = path_to_sizes["/local"]
    elif "/" in path_to_sizes:
        sizes = path_to_sizes["/"]
    else:
        raise RuntimeError("No /local or / found in df output")
    hdd_used, hdd_avail = map(int, sizes)

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
    host=config.get("mongo_host", "localhost"),
    port=int(config.get("mongo_port", 27017)),
    username=config.get("mongo_user", ""),
    password=config.get("mongo_pw", ""),
    authSource="admin",
) as client:
    db = client["gpustat"]

    machine_name = config.get("machine_name", "<unnamed>")
    log_interval = int(config.get("log_interval", 60))

    last_timestamp = datetime.datetime.now(datetime.timezone.utc)
    
    logger.info("Starting gpustat")
    while True:
        logger.info("Updating gpustat...")
        timestamp = datetime.datetime.now(datetime.timezone.utc)
        try:
            gpu_info = get_nvidia_stats()
            (
                nproc,
                lavg,
                mem_total,
                mem_used,
                hdd_avail,
                hdd_used,
                procs,
            ) = get_top_stats()

            machine_log = {
                "machineId": machine_name,
                "name": machine_name,
                "timestamp": timestamp,
                "log_interval": (timestamp - last_timestamp).total_seconds(),
                "gpus": gpu_info,
                "cpu": {
                    "nproc": nproc,
                    "load_avg": lavg,
                    "memory_used": mem_used * 1024,
                    "memory_total": mem_total * 1024,
                    "storage_used": hdd_used * 1024,
                    "storage_total": (hdd_used + hdd_avail) * 1024,
                    "procs": procs,
                },
            }
            db.machine_logs.insert_one(machine_log)

            logger.info(f"Updated {machine_name} stats")
        except Exception as e:
            logger.warning(e)
            traceback.print_exc()
        except sh.ErrorReturnCode_1 as e:
            logger.warning(e)
        last_timestamp = timestamp
        logger.info(f"Sleeping for {log_interval} seconds...")
        time.sleep(log_interval)
