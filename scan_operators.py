import json
import os
import pathlib
import sys
import time
import traceback

MAA_PATH = pathlib.Path(r"G:\Tools\MAA-v4.28.4-win-x64")
sys.path.insert(0, str(MAA_PATH / "Python"))

from asst.asst import Asst
from asst.utils import InstanceOptionType, Message

ADB_PATH = r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\nx_main\adb.exe"
ADB_ADDRESS = "127.0.0.1:16384"
CONFIG = "MuMuEmulator12"
OUTPUT_FILE = pathlib.Path(__file__).resolve().parent / "operators_data.json"

operators_data = {"own_opers": [], "all_oper": []}
scan_done = False
startup_done = False
close_done = False


def _merge_operators(target: list, source: list):
    """合并干员列表，按 id 去重"""
    existing_ids = {o["id"] for o in target}
    for oper in source:
        if oper["id"] not in existing_ids:
            target.append(oper)
            existing_ids.add(oper["id"])


@Asst.CallBackType
def my_callback(msg, details, arg):
    global scan_done, startup_done, close_done
    try:
        m = Message(msg)
        d = json.loads(details.decode("utf-8"))
    except Exception:
        return

    if m == Message.SubTaskExtraInfo:
        what = d.get("what", "")
        detail = d.get("details", {})

        if what in ("OperBox", "OperBoxInfo"):
            done = detail.get("done", False)

            if "own_opers" in detail and detail["own_opers"]:
                _merge_operators(operators_data["own_opers"], detail["own_opers"])

            if "all_oper" in detail and detail["all_oper"]:
                operators_data["all_oper"] = detail["all_oper"]

            own_count = len(operators_data["own_opers"])
            if not done:
                print(f"\r[扫描中] 已识别 {own_count} 名干员...", end="", flush=True)
            else:
                scan_done = True
                print(f"\r[完成] 共识别 {own_count} 名干员")

        elif what == "OperBoxNameCard":
            cards = detail.get("name_cards", [])
            if cards:
                _merge_operators(operators_data["own_opers"], cards)
                print(f"\r[扫描中] 已识别 {len(operators_data['own_opers'])} 名干员...", end="", flush=True)

    elif m == Message.SubTaskStart:
        print(f"[子任务开始] {d.get('subtask', '')}")
    elif m == Message.SubTaskCompleted:
        print(f"[子任务完成] {d.get('subtask', '')}")
    elif m == Message.TaskChainStart:
        tc = d.get("taskchain", "")
        print(f"[任务链开始] {tc}")
        if tc == "StartUp":
            startup_done = False
        elif tc == "CloseDown":
            close_done = False
    elif m == Message.TaskChainCompleted:
        tc = d.get("taskchain", "")
        print(f"[任务链结束] {tc}")
        if tc == "StartUp":
            startup_done = True
        elif tc == "CloseDown":
            close_done = True
    elif m == Message.ConnectionInfo:
        pass
    elif m == Message.InternalError:
        print(f"[内部错误] {d}")
    elif m == Message.InitFailed:
        print(f"[初始化失败] {d}")


def scan_operators(asst: Asst):
    """单次扫描：先回到主界面，再扫描干员"""
    global scan_done, startup_done
    scan_done = False
    startup_done = False

    print("\n[任务] 添加 StartUp (返回主界面)...")
    asst.append_task("StartUp", {
        "client_type": "Official",
        "start_game_enabled": False
    })

    print("[任务] 添加 OperBox (扫描干员)...")
    asst.append_task("OperBox", {})

    print("[执行] 开始扫描...\n")
    asst.start()

    while asst.running():
        time.sleep(0.5)
        if scan_done:
            asst.stop()
            break

    return len(operators_data["own_opers"])


def main():
    print("=" * 50)
    print("明日方舟干员扫描工具 (OperBox)")
    print("=" * 50)

    print(f"\n[初始化] 加载 MAA 资源: {MAA_PATH}")
    try:
        load_result = Asst.load(path=MAA_PATH)
    except Exception as e:
        print(f"[错误] Asst.load() 异常: {e}")
        traceback.print_exc()
        return

    if not load_result:
        print("[错误] 资源加载失败！")
        return

    try:
        ver = Asst._Asst__lib.AsstGetVersion().decode()
        print(f"[初始化] MAA 版本: {ver}")
    except Exception:
        print("[警告] 无法获取版本号")

    asst = Asst(callback=my_callback)
    asst.set_instance_option(InstanceOptionType.touch_type, "minitouch")

    print(f"\n[连接] 正在连接模拟器...")
    print(f"       ADB: {ADB_PATH}")
    print(f"       地址: {ADB_ADDRESS}")

    if not asst.connect(ADB_PATH, ADB_ADDRESS, CONFIG):
        print("[错误] 连接失败！")
        return

    print("[连接] 连接成功！")

    count = scan_operators(asst)

    if count == 0:
        print("\n[警告] 未识别到任何干员，可能是页面状态不对")
        print("[提示] 请确认游戏处于主界面后，手动关闭程序后重试")
    else:
        print("\n" + "=" * 50)
        print("[结果] 干员扫描完成！")
        print(f"       已拥有干员: {len(operators_data['own_opers'])} 名")
        print(f"       全干员列表: {len(operators_data['all_oper'])} 名")

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(operators_data, f, ensure_ascii=False, indent=2)
        print(f"\n[保存] 数据已写入: {OUTPUT_FILE}")

        print("\n[预览] 前 10 名干员:")
        for oper in operators_data["own_opers"][:10]:
            print(
                f"  {oper.get('name', '???'):<12s} "
                f"星级:{oper.get('rarity', '?')} "
                f"精英:{oper.get('elite', '?')} "
                f"等级:{oper.get('level', '?')} "
                f"潜能:{oper.get('potential', '?')}"
            )

        if len(operators_data["own_opers"]) > 10:
            print(f"  ... 还有 {len(operators_data['own_opers']) - 10} 名")


if __name__ == "__main__":
    main()
