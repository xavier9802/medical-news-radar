#!/bin/bash
echo "🛰  medical-radar · 零API · 零Key · 读取公开医疗雷达数据"
curl -s https://xavier9802.github.io/medical-news-radar/data/latest-24h.json -o /tmp/medical-radar-24h.json
python3 - <<'EOF'
import json, datetime
d = json.load(open('/tmp/medical-radar-24h.json'))
gen = d['generated_at'][:16].replace('T', ' ')
print(f"📡 数据时间 {gen} UTC | {d['total_items']} 条医疗信号 | {d['source_count']} 个信源")
print()
items = sorted(d['items'], key=lambda i: (-i.get('importance_score', 0), -i.get('medical_relevance_score', i.get('medical_score', 0))))
groups = [('policy', '📜 政策监管'), ('medical_ai', '🤖 医疗AI'), ('pharma_device', '💊 医药器械'), ('company_market', '🏢 企业动态')]
for category, title in groups:
    hits = [i for i in items if i.get('category') == category][:3]
    if not hits:
        continue
    print(title)
    for i in hits:
        t = i['title'][:46] + ('…' if len(i['title']) > 46 else '')
        print(f"  · {t}  ⟵ {i['source']}")
    print()
print("…完整简报含原文链接，可继续问：\"医保政策有什么变化\" / \"看下医疗AI故事线\"")
EOF
