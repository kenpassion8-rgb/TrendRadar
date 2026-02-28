#!/usr/bin/env python3
"""
poster_and_send.py
完整流程：读取TrendRadar结果 → Kimi提炼 → 生成2张海报 → 发送企业微信
放置位置：仓库根目录下的 scripts/poster_and_send.py
"""

import os
import json
import datetime
import requests
import base64
import hashlib
import subprocess
import random

# ══════════════════════════════════════════
# 从环境变量读取密钥（GitHub Secrets自动注入）
# ══════════════════════════════════════════
KIMI_API_KEY      = os.environ.get("KIMI_API_KEY", "")
WEBHOOK_URL       = os.environ.get("WEWORK_WEBHOOK_URL", "")
WECOM_CORP_ID     = os.environ.get("WECOM_CORP_ID", "")
WECOM_AGENT_ID    = os.environ.get("WECOM_AGENT_ID", "")
WECOM_APP_SECRET  = os.environ.get("WECOM_APP_SECRET", "")

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT   = os.path.dirname(SCRIPT_DIR)
AVATAR_PATH = os.path.join(REPO_ROOT, "scripts", "avatar.jpg")
QR_PATH     = os.path.join(REPO_ROOT, "scripts", "qrcode.png")
OUTPUT_DIR  = os.path.join(REPO_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ══════════════════════════════════════════
# 1. 读取 TrendRadar 输出 / 让 Kimi 生成
# ══════════════════════════════════════════

def load_trendradar_news() -> list:
    """尝试读取 TrendRadar 抓取的新闻"""
    json_path = os.path.join(REPO_ROOT, "output", "latest.json")
    if not os.path.exists(json_path):
        print("⚠️  未找到 TrendRadar 输出文件，将由 Kimi 直接生成资讯")
        return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else data.get("items", data.get("news", []))
        keywords = ["外贸","汇率","跨境","亚马逊","速卖通","关税","物流","海运","开发客户","询盘","独立站","进出口","商务部","供应链"]
        filtered = [i for i in items if any(k in (i.get("title","") + i.get("description","")) for k in keywords)]
        print(f"✅ TrendRadar 找到 {len(filtered)} 条外贸相关新闻")
        return filtered[:15]
    except Exception as e:
        print(f"⚠️  读取失败: {e}")
        return []


def call_kimi(prompt: str) -> str:
    """调用 Kimi API"""
    resp = requests.post(
        "https://api.moonshot.cn/v1/chat/completions",
        headers={"Authorization": f"Bearer {KIMI_API_KEY}", "Content-Type": "application/json"},
        json={"model": "moonshot-v1-32k", "messages": [{"role": "user", "content": prompt}], "max_tokens": 2500},
        timeout=60
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def get_5_news(raw_items: list) -> list:
    """从 TrendRadar 数据或直接让 Kimi 生成 5 条结构化新闻"""
    today = datetime.datetime.now().strftime("%Y年%m月%d日")

    if raw_items:
        news_text = "\n".join([f"{i+1}. 【{n.get('source','')}】{n.get('title','')}\n   {n.get('description','')[:100]}" for i, n in enumerate(raw_items)])
        prompt = f"""今天是{today}。以下是从各平台抓取的外贸新闻原文，请挑选5条最有价值的，整理成外贸业务员最关心的资讯。

{news_text}

只输出JSON数组，不要任何说明：
[
  {{
    "tag": "话题标签（从以下选：💱 汇率动态 / 🌐 贸易政策 / 📦 平台动态 / 🚢 物流资讯 / 🎯 开发客户 / 🏭 供应链）",
    "headline": "标题（15字内，含数字或关键变化）",
    "body": "正文（55-70字，说清楚：发生什么事+对外贸的影响+外贸人怎么做）",
    "highlight": "正文中需高亮的关键词（5-10字）"
  }}
]
共5条。"""
    else:
        topics = [
            ("💱 汇率动态", "人民币汇率最新走势，结汇购汇建议"),
            ("🌐 贸易政策", "最新关税政策或商务部外贸通知"),
            ("📦 平台动态", "亚马逊或速卖通最新规则变化"),
            ("🚢 物流资讯", "国际海运空运运费最新动态"),
            ("🎯 开发客户", "外贸开发海外客户的最新技巧或市场信息"),
            ("🏭 供应链", "跨境供应链或工厂生产最新动态"),
        ]
        selected = random.sample(topics, 5)
        topics_str = "\n".join([f"  {t[0]}：{t[1]}" for t in selected])
        prompt = f"""今天是{today}。你是专业外贸资讯编辑，请针对以下5个方向，各总结一条最近2天内真实发生的外贸资讯：

{topics_str}

只输出JSON数组，不要任何说明：
[
  {{
    "tag": "话题标签（含emoji，如上所列）",
    "headline": "标题（15字内，含具体数字或关键词）",
    "body": "正文（55-70字，含具体信息+外贸人实操建议）",
    "highlight": "需高亮的关键词（5-10字）"
  }}
]
共5条。"""

    raw = call_kimi(prompt)
    # 清理 markdown
    text = raw.strip()
    if "```" in text:
        for part in text.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("["):
                text = part
                break
    try:
        return json.loads(text)
    except:
        print(f"⚠️  JSON解析失败，使用兜底数据")
        return get_fallback_news()


def get_fallback_news():
    m = datetime.datetime.now().strftime("%m月%d日")
    return [
        {"tag":"💱 汇率动态","headline":f"{m}人民币汇率参考","body":"今日人民币兑美元汇率维持稳定。出口企业建议关注近期汇率波动，可通过银行远期结汇提前锁定汇率，保障利润不受汇率影响。","highlight":"远期结汇"},
        {"tag":"🌐 贸易政策","headline":"商务部推进通关便利化改革","body":"商务部持续推动通关便利化，压缩整体通关时间。建议外贸企业申请AEO认证，享受绿色通道优先验放等待遇，降低物流成本。","highlight":"AEO认证"},
        {"tag":"📦 平台动态","headline":"亚马逊调整FBA仓储费用标准","body":"亚马逊最新公告调整FBA仓储费收费标准，长期库存附加费同步更新。建议卖家及时清理滞销库存，优化备货节奏，避免产生额外费用。","highlight":"长期库存附加费"},
        {"tag":"🚢 物流资讯","headline":"跨太平洋航线运费小幅回调","body":"本周跨太平洋航线集装箱运费小幅回调。业内预计短期内运力供给充足，建议外贸企业把握时机提前预订舱位，锁定较低运费成本。","highlight":"提前预订舱位"},
        {"tag":"🎯 开发客户","headline":"LinkedIn开发信个性化回复率提升3倍","body":"研究显示个性化开发信比模板邮件回复率高3倍。建议外贸业务员发信前先研究客户官网，在首段提炼1-2个针对性痛点，提升询盘转化率。","highlight":"个性化开发信"},
    ]

# ══════════════════════════════════════════
# 2. 生成海报 HTML
# ══════════════════════════════════════════

def load_b64(path, mime):
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"

def build_html(news_list: list, poster_num: int) -> str:
    """生成单张海报 HTML，poster_num=1 显示第1-3条，poster_num=2 显示第4-5条"""
    now = datetime.datetime.now()
    year = now.strftime("%Y")
    md   = now.strftime("%m.%d")
    week = ["星期一","星期二","星期三","星期四","星期五","星期六","星期日"][now.weekday()]

    avatar_src = load_b64(AVATAR_PATH, "image/jpeg") if os.path.exists(AVATAR_PATH) else ""
    qr_src     = load_b64(QR_PATH,     "image/png")  if os.path.exists(QR_PATH)     else ""

    # 第1张：3条；第2张：2条
    items = news_list[:3] if poster_num == 1 else news_list[3:5]
    label = f"① 共2张" if poster_num == 1 else f"② 共2张"

    cards = ""
    for n in items:
        body = n.get("body","")
        hl   = n.get("highlight","")
        if hl and hl in body:
            body = body.replace(hl, f'<span class="hl">{hl}</span>', 1)
        cards += f"""
        <div class="card">
          <div class="card-inner">
            <div class="tag">{n.get("tag","📰 外贸资讯")}</div>
            <div class="headline">{n.get("headline","")}</div>
            <div class="body">{body}</div>
          </div>
        </div>"""

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Ma+Shan+Zheng&family=Noto+Serif+SC:wght@700;900&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#0d3b2e;font-family:'Noto Sans SC',sans-serif;}}
.poster{{width:780px;background:linear-gradient(170deg,#0d3b2e 0%,#0a2e22 30%,#071f18 65%,#040e0b 100%);position:relative;overflow:hidden;}}
.bg-grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.018) 1px,transparent 1px);background-size:40px 40px;}}
.bg-glow{{position:absolute;top:80px;left:50%;transform:translateX(-50%);width:600px;height:400px;background:radial-gradient(circle,rgba(32,180,120,.10) 0%,transparent 65%);pointer-events:none;}}
.bg-mtn{{position:absolute;bottom:220px;left:-30px;right:-30px;height:180px;background:radial-gradient(ellipse at 50% 110%,#0f5040 0%,#083325 40%,transparent 68%);opacity:.4;border-radius:50%;transform:scaleX(1.4);}}
.header{{position:relative;z-index:10;display:flex;justify-content:space-between;align-items:center;padding:32px 40px 0;}}
.profile{{display:flex;align-items:center;gap:14px;}}
.avatar{{width:76px;height:76px;border-radius:50%;border:3px solid rgba(32,180,120,.7);overflow:hidden;flex-shrink:0;box-shadow:0 0 0 1px rgba(32,180,120,.3),0 4px 16px rgba(0,0,0,.4);}}
.avatar img{{width:100%;height:100%;object-fit:cover;object-position:center top;}}
.name{{font-size:24px;color:rgba(255,255,255,.88);letter-spacing:3px;font-family:'Noto Serif SC',serif;font-weight:700;}}
.date-box{{background:rgba(255,255,255,.96);border-radius:12px;padding:10px 18px;text-align:center;min-width:124px;border:1.5px solid rgba(32,180,120,.5);box-shadow:0 4px 20px rgba(0,0,0,.3);}}
.date-year{{font-size:20px;font-weight:900;color:#0a3d2e;letter-spacing:2px;line-height:1;}}
.date-day{{font-size:28px;font-weight:900;color:#0a3d2e;letter-spacing:1px;line-height:1.3;}}
.date-week{{font-size:13px;color:#1a6b50;letter-spacing:2px;border-top:1.5px solid rgba(10,61,46,.25);margin-top:4px;padding-top:4px;font-weight:600;}}
.title-area{{position:relative;z-index:10;padding:8px 40px 0;text-align:center;}}
.main-title{{font-family:'Ma Shan Zheng','Noto Serif SC',serif;font-weight:900;line-height:1.05;background:linear-gradient(175deg,rgba(255,255,255,.97) 0%,rgba(140,235,195,.80) 45%,rgba(30,130,85,.40) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;letter-spacing:8px;}}
.t1,.t2{{font-size:136px;display:block;}}
.t2{{margin-top:-8px;}}
.sub-tag{{display:inline-block;background:linear-gradient(90deg,#16a673,#0d7a54);color:white;font-size:16px;letter-spacing:5px;padding:6px 24px;border-radius:30px;margin-top:8px;font-weight:500;}}
.page-badge{{display:inline-block;font-size:13px;color:rgba(255,255,255,.4);letter-spacing:2px;margin-top:6px;}}
.divider{{position:relative;z-index:10;margin:18px 40px;height:1.5px;background:linear-gradient(90deg,transparent,rgba(32,180,120,.55),transparent);}}
.news{{position:relative;z-index:10;padding:0 30px;display:flex;flex-direction:column;gap:16px;}}
.card{{background:rgba(255,255,255,.042);border:1.5px solid rgba(32,180,120,.22);border-radius:16px;padding:20px;position:relative;overflow:hidden;}}
.card::before{{content:'';position:absolute;top:0;left:0;width:5px;height:100%;background:linear-gradient(180deg,#20b478,#0d7a54);border-radius:5px 0 0 5px;}}
.card-inner{{padding-left:16px;}}
.tag{{display:inline-flex;align-items:center;gap:6px;font-size:16px;color:#20b478;letter-spacing:1.5px;font-weight:700;margin-bottom:8px;background:rgba(32,180,120,.12);padding:3px 12px;border-radius:6px;}}
.headline{{font-size:22px;font-weight:700;color:rgba(255,255,255,.94);line-height:1.5;margin-bottom:7px;font-family:'Noto Serif SC',serif;}}
.body{{font-size:18px;color:rgba(255,255,255,.55);line-height:1.7;}}
.hl{{color:#7efcd4;font-weight:600;}}
.footer{{position:relative;z-index:10;margin-top:18px;padding:0 40px 30px;}}
.fdiv{{height:1.5px;background:linear-gradient(90deg,transparent,rgba(32,180,120,.45),transparent);margin-bottom:16px;}}
.disc{{text-align:center;font-size:16px;color:rgba(255,255,255,.28);margin-bottom:12px;letter-spacing:1px;}}
.fcontent{{display:flex;align-items:center;justify-content:space-between;gap:18px;}}
.fcta{{font-size:22px;color:rgba(255,255,255,.92);font-weight:700;line-height:1.7;font-family:'Noto Serif SC',serif;}}
.fsub{{font-size:16px;color:rgba(255,255,255,.45);margin-top:5px;letter-spacing:1px;}}
.qr{{width:130px;height:130px;background:white;border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;overflow:hidden;padding:5px;box-shadow:0 4px 20px rgba(0,0,0,.4);}}
.qr img{{width:100%;height:100%;object-fit:contain;}}
</style></head><body>
<div class="poster">
  <div class="bg-grid"></div><div class="bg-glow"></div><div class="bg-mtn"></div>
  <div class="header">
    <div class="profile">
      <div class="avatar"><img src="{avatar_src}"/></div>
      <div class="name">阿K外贸人</div>
    </div>
    <div class="date-box">
      <div class="date-year">{year}</div>
      <div class="date-day">{md}</div>
      <div class="date-week">{week}</div>
    </div>
  </div>
  <div class="title-area">
    <div class="main-title"><span class="t1">外贸</span><span class="t2">日报</span></div>
    <div class="sub-tag">FOREIGN TRADE DAILY</div><br>
    <span class="page-badge">{label}</span>
  </div>
  <div class="divider"></div>
  <div class="news">{cards}</div>
  <div class="footer">
    <div class="disc">资讯仅供参考，不构成投资或操作建议</div>
    <div class="fdiv"></div>
    <div class="fcontent">
      <div>
        <div class="fcta">关注「阿K外贸人」<br>每日外贸资讯不错过</div>
        <div class="fsub">扫码 · 获取更多外贸干货</div>
      </div>
      <div class="qr"><img src="{qr_src}"/></div>
    </div>
  </div>
</div></body></html>"""


def html_to_png(html: str, out_path: str):
    """用 Playwright 把 HTML 渲染成 PNG"""
    tmp_html = out_path.replace(".png", "_tmp.html")
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(html)

    js = f"""
const {{chromium}} = require('playwright');
(async()=>{{
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.setViewportSize({{width:780,height:1700}});
  await p.setContent(require('fs').readFileSync('{tmp_html}','utf8'),{{waitUntil:'networkidle'}});
  await p.waitForTimeout(3500);
  const el = await p.$('.poster');
  await el.screenshot({{path:'{out_path}',type:'png'}});
  await b.close();
  console.log('OK');
}})();"""
    tmp_js = out_path.replace(".png", "_tmp.js")
    with open(tmp_js, "w") as f:
        f.write(js)

    r = subprocess.run(["node", tmp_js], capture_output=True, text=True, timeout=60)
    os.remove(tmp_html)
    os.remove(tmp_js)
    if r.returncode != 0:
        raise RuntimeError(f"截图失败: {r.stderr[:300]}")
    print(f"✅ 海报生成: {out_path}")

# ══════════════════════════════════════════
# 3. 发送到企业微信
# ══════════════════════════════════════════

def send_image_webhook(image_path: str):
    """群机器人发图片"""
    if not WEBHOOK_URL:
        print("⚠️  WEBHOOK_URL 未设置，跳过群发送")
        return
    with open(image_path, "rb") as f:
        data = f.read()
    payload = {
        "msgtype": "image",
        "image": {
            "base64": base64.b64encode(data).decode(),
            "md5": hashlib.md5(data).hexdigest()
        }
    }
    r = requests.post(WEBHOOK_URL, json=payload, timeout=30)
    result = r.json()
    if result.get("errcode") == 0:
        print("✅ 群机器人图片发送成功")
    else:
        print(f"❌ 群机器人发送失败: {result}")


def send_text_webhook(text: str):
    """群机器人发文字"""
    if not WEBHOOK_URL:
        return
    requests.post(WEBHOOK_URL, json={"msgtype":"text","text":{"content":text}}, timeout=30)
    print("✅ 群机器人文字发送成功")


def get_app_token() -> str:
    """获取企业微信应用 access_token"""
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={WECOM_CORP_ID}&corpsecret={WECOM_APP_SECRET}"
    r = requests.get(url, timeout=15)
    d = r.json()
    if d.get("errcode") == 0:
        return d["access_token"]
    raise Exception(f"获取token失败: {d}")


def upload_image(token: str, image_path: str) -> str:
    """上传图片获取 media_id"""
    url = f"https://qyapi.weixin.qq.com/cgi-bin/media/upload?access_token={token}&type=image"
    with open(image_path, "rb") as f:
        r = requests.post(url, files={"media": (os.path.basename(image_path), f, "image/png")}, timeout=30)
    d = r.json()
    if d.get("errcode") == 0:
        return d["media_id"]
    raise Exception(f"上传图片失败: {d}")


def send_app_image(token: str, media_id: str):
    """应用发图片给个人"""
    if not WECOM_CORP_ID:
        print("⚠️  企业微信应用信息未配置，跳过个人发送")
        return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
    payload = {"touser":"@all","msgtype":"image","agentid":int(WECOM_AGENT_ID),"image":{"media_id":media_id}}
    r = requests.post(url, json=payload, timeout=30)
    d = r.json()
    if d.get("errcode") == 0:
        print("✅ 应用图片发送成功")
    else:
        print(f"❌ 应用图片发送失败: {d}")


def send_app_text(token: str, text: str):
    """应用发文字给个人"""
    if not WECOM_CORP_ID:
        return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
    payload = {"touser":"@all","msgtype":"text","agentid":int(WECOM_AGENT_ID),"text":{"content":text}}
    requests.post(url, json=payload, timeout=30)
    print("✅ 应用文字发送成功")

# ══════════════════════════════════════════
# 4. 生成朋友圈文案
# ══════════════════════════════════════════

def build_copywriting(news_list: list) -> str:
    today = datetime.datetime.now().strftime("%Y.%m.%d")
    lines = [f"📊 外贸早报 | {today}\n"]
    for n in news_list:
        clean_body = n["body"].replace('<span class="hl">','').replace('</span>','')
        lines.append(f"{n['tag']}\n「{n['headline']}」\n{clean_body[:40]}...\n")
    lines.append("每天1分钟，掌握一线外贸动态。\n关注「阿K外贸人」持续更新 👇\n\n#外贸 #跨境电商 #外贸业务员 #外贸日报")
    return "\n".join(lines)

# ══════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════

def main():
    print("="*50)
    print(f"🚀 外贸日报 | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)

    # Step 1: 获取新闻
    print("\n🔍 Step1: 获取外贸资讯...")
    raw = load_trendradar_news()
    news5 = get_5_news(raw)
    print(f"✅ 共获取 {len(news5)} 条新闻")

    # Step 2: 生成2张海报
    print("\n🖼️  Step2: 生成海报图片...")
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    poster1_path = os.path.join(OUTPUT_DIR, f"poster_{today_str}_1.png")
    poster2_path = os.path.join(OUTPUT_DIR, f"poster_{today_str}_2.png")

    html_to_png(build_html(news5, 1), poster1_path)
    html_to_png(build_html(news5, 2), poster2_path)

    # Step 3: 生成文案
    copywriting = build_copywriting(news5)

    # Step 4: 发送
    print("\n📤 Step3: 发送到企业微信...")

    # 群机器人：发2张图 + 文案
    send_image_webhook(poster1_path)
    send_image_webhook(poster2_path)
    send_text_webhook(copywriting)

    # 应用（个人手机）：发2张图 + 文案
    if WECOM_CORP_ID and WECOM_APP_SECRET:
        try:
            token = get_app_token()
            mid1  = upload_image(token, poster1_path)
            mid2  = upload_image(token, poster2_path)
            send_app_image(token, mid1)
            send_app_image(token, mid2)
            send_app_text(token, copywriting)
        except Exception as e:
            print(f"❌ 应用发送异常: {e}")
    else:
        print("⚠️  企业微信应用未配置，仅发送群机器人")

    print("\n🎉 全部完成！")


if __name__ == "__main__":
    main()
