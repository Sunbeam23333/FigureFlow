#!/usr/bin/env python3
"""Editable reconstruction from CARE Transformer Table 1, not original plot code."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8, 'pdf.fonttype': 42})
rows = list(csv.DictReader((HERE / 'data.csv').open(newline='')))
styles = {
    'CARE': ('#df1745', 'Our CARE (LA+CONV)'),
    'EMO': ('#f4b57c', "EMO ICCV'23 (SA+CONV)"),
    'MobileViG': ('#b97f61', "MobileViG CVPR'23 (GNN+CONV)"),
    'MobileViGv2': ('#00df22', "MobileViGv2 CVPR'24 (GNN+CONV)"),
    'MobileOne': ('#9227e8', "MobileOne ICCV'23 (CONV)"),
    'FastViT': ('#00008b', "FastViT CVPR'23 (SA+CONV)"),
    'EdgeViT': ('#008f8a', "EdgeViT ECCV'22 (SA+CONV)"),
    'MobileAtt': ('#ed00ed', "MobileAtt ICLR'24 (LA+CONV)"),
}
fig, ax = plt.subplots(figsize=(4.9, 3.55))
for family, (color, label) in styles.items():
    data = [r for r in rows if r['family'] == family]
    data.sort(key=lambda r: float(r['latency_ms']))
    x = [float(r['latency_ms']) for r in data]
    y = [float(r['top1_pct']) for r in data]
    if family == 'CARE':
        ax.plot(x, y, '--', color=color, lw=1.2, label=label, zorder=4)
        ax.scatter(x, y, s=75, marker='*', c=color, zorder=5)
        for r in data:
            offsets = {'CARE-S0': (-5, 4), 'CARE-S1': (5, 5), 'CARE-S2': (5, -2)}
            anchor = 'right' if r['model'] == 'CARE-S0' else 'left'
            ax.annotate(r['model'], (float(r['latency_ms']), float(r['top1_pct'])),
                        xytext=offsets[r['model']], textcoords='offset points', fontsize=7,
                        fontweight='bold', ha=anchor)
    else:
        ax.plot(x, y, color=color, lw=8, alpha=.5, solid_capstyle='round', label=label, zorder=2)
        ax.scatter(x, y, s=[30 + 60 * float(r['gmac']) for r in data],
                   color=color, alpha=.95, edgecolors='none', zorder=3)
ax.set_xlim(54, 8.5); ax.set_ylim(71, 82.5)
ax.set_xticks([50, 40, 30, 20, 10]); ax.set_yticks([72, 74, 76, 78, 80, 82])
ax.grid(True, linestyle='--', color='#dddddd', lw=.6)
ax.set_xlabel('Latency (ms)'); ax.set_ylabel('Top-1 Acc (%) on ImageNet-1K')
for spine in ax.spines.values(): spine.set_color('#999999')
ax.legend(loc='lower left', fontsize=6.2, framealpha=.85, handlelength=3)
fig.tight_layout(pad=.4)
for suffix in ('pdf', 'png'):
    fig.savefig(HERE / ('care_transformer_fig1_reconstruction.' + suffix), dpi=240)
plt.close(fig)
