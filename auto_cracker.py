#!/usr/bin/env python3
"""
一键处理脚本：
1. 从注册表读取 hzyks 协议路径，切换到 resources 目录
2. 备份 app.asar 和 fsdeamon.exe
3. 解包 app.asar，修改 src/main.js 中的函数名
4. 重新封包 app.asar
5. 生成 fsdeamon.py并打包为 fsdeamon.exe
6. 清理临时文件
"""

import os
import shutil
import subprocess
import sys
import winreg
from pathlib import Path
from PyInstaller import __main__ as pyi

# 检查并导入所需库
try:
    from asar import extract_archive, create_archive
except ImportError:
    print("错误: 未安装 asar 库。请运行: pip install asar")
    sys.exit(1)

try:
    import PyInstaller
except ImportError:
    print("错误: 未安装 PyInstaller。请运行: pip install pyinstaller")
    sys.exit(1)

def get_resources_dir_from_registry():
    """从注册表获取 hzyks 协议处理器的路径，并返回 resources 目录"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"hzyks\shell\open\command")
        value, _ = winreg.QueryValueEx(key, "")  # 默认值
        winreg.CloseKey(key)
    except FileNotFoundError:
        print("❌ 未找到注册表键 HKEY_CLASSES_ROOT\\hzyks\\shell\\open\\command")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 读取注册表失败: {e}")
        sys.exit(1)

    # 解析命令，提取 exe 路径（支持引号包裹）
    import shlex
    parts = shlex.split(value)
    if not parts:
        print("❌ 无法解析注册表命令")
        sys.exit(1)
    exe_path = Path(parts[0]).resolve()
    if not exe_path.exists():
        print(f"❌ 解析出的 exe 路径不存在: {exe_path}")
        sys.exit(1)

    # 计算 resources 目录：exe 所在目录下的 resources
    # 例如 exe 位于 D:\Program Files (x86)\yksfullexam\Fullscreenexammodule.exe
    # 则 resources 目录应为 D:\Program Files (x86)\yksfullexam\resources
    resources_dir = exe_path.parent / "resources"
    if not resources_dir.is_dir():
        print(f"❌ resources 目录不存在: {resources_dir}")
        sys.exit(1)

    return resources_dir

def backup_file(file_path: Path):
    """如果文件存在，则创建备份（文件名.bak）"""
    if file_path.exists():
        backup_path = file_path.with_suffix(file_path.suffix + '.bak')
        shutil.copy2(file_path, backup_path)
        print(f"✅ 已备份 {file_path} -> {backup_path}")
    else:
        print(f"⚠️  警告：{file_path} 不存在，跳过备份")

def modify_asar(asar_path: Path, extract_dir: Path):
    """解包、修改、封包 ASAR 文件"""
    target_file = extract_dir / "src" / "main.js"

    # 解包
    print("📦 正在解包 app.asar ...")
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_archive(asar_path, extract_dir)

    # 检查目标文件
    if not target_file.is_file():
        print(f"❌ 错误：未找到 {target_file}，请检查解包后的文件结构。")
        sys.exit(1)

    # 读取并替换内容
    print(f"✏️  正在修改 {target_file} ...")
    with open(target_file, 'r', encoding='utf-8') as f:
        content = f.read()

    modified = content.replace('setAlwaysOnTop', 'setFocusable').replace('setContentProtection', 'setFocusable')

    with open(target_file, 'w', encoding='utf-8') as f:
        f.write(modified)

    print("✅ 替换完成。")

    # 重新封包
    print("📦 正在重新封包 app.asar ...")
    create_archive(extract_dir, asar_path)

    # 删除临时目录
    shutil.rmtree(extract_dir)
    print(f"🧹 临时目录 {extract_dir} 已删除。")

def generate_fsdeamon_py(path: Path):
    """生成 fsdeamon.py 文件"""
    content = '''import threading
import time
import os
import psutil
from flask import Flask, request, jsonify
import json

def check_process():
    """后台线程：检测 Fullscreenexammodule.exe 是否存在，不存在则退出"""
    while True:
        time.sleep(1)
        try:
            found = False
            for proc in psutil.process_iter(['name']):
                # 比较进程名（不区分大小写）
                if proc.info['name'] and 'fullscreenexammodule.exe' == proc.info['name'].lower():
                    found = True
                    break
            if not found:
                os._exit(0)  # 进程不存在，强制退出
        except Exception:
            # 发生任何错误也退出，避免程序僵死
            os._exit(1)

# 启动守护线程
thread = threading.Thread(target=check_process, daemon=True)
thread.start()

app = Flask(__name__)

@app.route('/check/canenter', methods=['GET'])
def check_can_enter():
    d_param = request.args.get('d', '')
    token = d_param[:32]
    response_data = {
        "result": "exam",
        "status": "ok",
        "token": token
    }
    return jsonify(response_data)

@app.route('/check/quit', methods=['GET'])
def quit():
    response_data = {
        "status": "ok"
    }
    return jsonify(response_data)

@app.route('/exam/startup', methods=['GET'])
def exam_startup():
    callback = request.args.get('callback', '')
    response_data = {
        "result": "setup ready",
        "status": "ok"
    }
    if callback:
        json_data = json.dumps(response_data)
        response = f"{callback}({json_data});"
        return response, 200, {'Content-Type': 'application/javascript'}
    else:
        return jsonify(response_data)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=40360, debug=False)
'''
    path.write_text(content, encoding='utf-8')
    print(f"✅ 已生成 {path}")

def package_script(script_path, options=None):
    """
    使用 PyInstaller 打包指定的 Python 脚本
    script_path: 要打包的脚本路径
    options: 额外的 PyInstaller 参数列表（例如 ['--onefile', '--name=myapp']）
    """
    if options is None:
        options = []
    # 构建完整的 PyInstaller 命令行参数
    args = [script_path] + options
    # 调用 PyInstaller 的 main 函数
    pyi.run(args)

def build_exe(py_path: Path):
    """使用 PyInstaller 打包为 exe"""
    print("🔨 正在打包 fsdeamon.exe ...")
    try:
        package_script(
            str(py_path),
            [
                "--onefile",
                "--noconsole",
                "--distpath", ".",
                "--workpath", "build_temp",
                "--specpath", "build_temp"
            ]
        )
        # 移动生成的 exe 到当前目录（如果不在）
        exe_name = py_path.stem + '.exe'
        if Path(exe_name).exists():
            # 已经在当前目录
            pass
        else:
            # 可能在 dist 文件夹，移动过来
            dist_exe = Path('dist') / exe_name
            if dist_exe.exists():
                shutil.move(str(dist_exe), exe_name)
        # 清理临时构建文件夹
        shutil.rmtree('build_temp', ignore_errors=True)
        shutil.rmtree('dist', ignore_errors=True)
        shutil.rmtree('build', ignore_errors=True)
        # .spec 文件已在 build_temp 中一并删除
        print(f"✅ 成功生成 {exe_name}")
    except subprocess.CalledProcessError as e:
        print(f"❌ 打包失败：{e.stderr}")
        sys.exit(1)

def main():
    # 1. 从注册表获取目标目录并切换
    target_dir = get_resources_dir_from_registry()
    print(f"📁 目标目录: {target_dir}")
    os.chdir(target_dir)

    # 2. 定义文件路径
    asar_file = Path("app.asar")
    exe_file = Path("fsdeamon.exe")
    extract_dir = Path("extracted")
    fsdeamon_py = Path("fsdeamon.py")

    # 3. 备份
    print("🔄 正在备份原文件...")
    backup_file(asar_file)
    backup_file(exe_file)

    # 4. 修改 ASAR
    modify_asar(asar_file, extract_dir)

    # 5. 生成 fsdeamon.py
    generate_fsdeamon_py(fsdeamon_py)

    # 6. 打包为 exe
    build_exe(fsdeamon_py)

    # 7. 清理生成的 .py 文件
    fsdeamon_py.unlink()
    print("🧹 已删除临时 fsdeamon.py")

    print("\n🎉 所有操作成功完成！")
    print(f"   - {asar_file} 已修改（原文件已备份为 {asar_file}.bak）")
    print(f"   - {exe_file} 已备份（如存在）")
    print(f"   - 新的 {exe_file} 已生成")

if __name__ == "__main__":
    main()
