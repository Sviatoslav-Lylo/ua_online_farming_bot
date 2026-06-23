#!/usr/bin/env python3
"""
Miner Bot Analytics Dashboard Generator
Processes automated harvesting logs to generate visual analytics and performance summaries.
"""

import os
import glob
import pandas as pd
import matplotlib.pyplot as plt

# ─────────────────────────────────────────────────────────────
# CONFIGURATION & CONSTANTS
# ─────────────────────────────────────────────────────────────
INPUT_DIR = "statistics"
OUTPUT_DIR = "analytics_output"

ORE_TYPES = ["bronze", "silver", "gold", "unknown", "stolen"]

ORE_PRICES = {
    "gold": 50000,
    "silver": 15000,
    "bronze": 1000,
    "unknown": 0,
    "stolen": 0
}

# Thematic color matching for professional visualization profiles
VISUAL_COLORS = {
    "gold": "#FFD900",      # Vibrant Gold
    "silver": "#C0C0C0",    # Metallic Silver
    "bronze": "#CD7F32",    # Deep Bronze
    "unknown": "#A9A9A9",   # Dark Gray
    "stolen": "#FF4500"     # Danger Orange/Red
}

def generate_dashboard(df, session_title, output_filename):
    """
    Generates a complete 3x3 dashboard layout including distribution metrics
    and comprehensive 24-hour frequency histograms.
    """
    if df.empty:
        print(f"[WARN] Dataframe for '{session_title}' is empty. Skipping visual rendering.")
        return

    # Ensure datetime columns and hours are extracted cleanly
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['hour'] = df['timestamp'].dt.hour

    # Calculate absolute count frequencies across all designated categories
    counts = df['ore_type'].value_counts().reindex(ORE_TYPES, fill_value=0)
    
    # Calculate financial metrics
    earnings = pd.Series({ore: counts[ore] * ORE_PRICES[ore] for ore in ORE_TYPES})
    earnings_filtered = earnings[earnings > 0]
    total_money = earnings.sum()

    # Initialize a high-fidelity visual layout matrix
    fig = plt.figure(figsize=(18, 13))
    fig.suptitle(f"MINER BOT PERFORMANCE DASHBOARD\nSource: {session_title}", fontsize=16, fontweight='bold', y=0.98)
    
    gs = fig.add_gridspec(3, 3, height_ratios=[1.1, 1.0, 1.0])

    # ── PIE CHART 1: Quantity Proportions (All nodes included) ──
    ax_pie_qty = fig.add_subplot(gs[0, 0])
    labels_qty = [f"{ore.upper()} ({count})" for ore, count in counts.items()]
    ax_pie_qty.pie(
        counts, 
        labels=labels_qty, 
        autopct=lambda p: '{:.1f}%'.format(p) if p > 0 else '', 
        colors=[VISUAL_COLORS[ore] for ore in counts.index], 
        startangle=140,
        textprops={'fontsize': 10}
    )
    ax_pie_qty.set_title("Harvested Node Proportions", fontsize=12, fontweight='bold', pad=10)

    # ── PIE CHART 2: Financial Contribution ( Profitable nodes only ) ──
    ax_pie_cash = fig.add_subplot(gs[0, 1])
    if not earnings_filtered.empty:
        labels_cash = [f"{ore.upper()} (${val:,})" for ore, val in earnings_filtered.items()]
        ax_pie_cash.pie(
            earnings_filtered, 
            labels=labels_cash, 
            autopct='%1.1f%%', 
            colors=[VISUAL_COLORS[ore] for ore in earnings_filtered.index], 
            startangle=140,
            textprops={'fontsize': 10}
        )
    else:
        ax_pie_cash.text(0.5, 0.5, "Zero Market Value Collected", ha='center', va='center', color='red', fontsize=12)
    ax_pie_cash.set_title("Revenue Distribution (Virtual Currency)", fontsize=12, fontweight='bold', pad=10)

    # ── METRIC SUMMARY BOX (Integrated Session Metadata) ──
    ax_summary = fig.add_subplot(gs[0, 2])
    ax_summary.axis('off')
    
    metrics_block = f"Session Runtime Data Summary:\n\n"
    for ore in ORE_TYPES:
        metrics_block += f" • {ore.upper().ljust(8)}: {counts[ore]:>4} units\n"
    metrics_block += f"\nTotal Gross Profit: ${total_money:,}\n"
    metrics_block += f"Total Yield Volume: {len(df)} nodes"

    ax_summary.text(
        0.1, 0.5, metrics_block,
        fontfamily='monospace', fontsize=11, va='center',
        bbox=dict(boxstyle="round,pad=1.2", facecolor="#ffffff", edgecolor="#dcdcdc")
    )

    # ── FREQUENCY HISTOGRAMS (24 Hourly Uniform Column Slices) ──
    # Axis configuration helper function
    def format_histogram_axis(ax, title, color_theme):
        ax.set_title(title, fontsize=11, fontweight='semibold')
        ax.set_xticks(range(24))
        ax.set_xlim(-0.5, 23.5)
        ax.set_xlabel("Hour of Day (24h format)", fontsize=9)
        ax.set_ylabel("Harvest Events Count", fontsize=9)
        ax.grid(axis='y', linestyle='--', alpha=0.5)

    # 1. Composite Timeline (All Ores Aggregated)
    ax_hist_all = fig.add_subplot(gs[1, 0])
    hourly_all = df['hour'].value_counts().reindex(range(24), fill_value=0)
    ax_hist_all.bar(range(24), hourly_all, color='#4682B4', edgecolor='#2f4f4f', alpha=0.9)
    format_histogram_axis(ax_hist_all, "Timeline Frequency: COMBINED TOTAL YIELD", '#4682B4')

    # 2. Sequential distribution layout map for specific types
    layout_mapping = [
        ("gold", gs[1, 1]),
        ("silver", gs[1, 2]),
        ("bronze", gs[2, 0]),
        ("unknown", gs[2, 1]),
        ("stolen", gs[2, 2])
    ]

    for ore_name, grid_cell in layout_mapping:
        ax_sub = fig.add_subplot(grid_cell)
        df_sub = df[df['ore_type'] == ore_name]
        hourly_sub = df_sub['hour'].value_counts().reindex(range(24), fill_value=0)
        
        ax_sub.bar(range(24), hourly_sub, color=VISUAL_COLORS[ore_name], edgecolor='#333333', alpha=0.9)
        format_histogram_axis(ax_sub, f"Timeline Frequency: {ore_name.upper()}", VISUAL_COLORS[ore_name])

    plt.tight_layout()
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    plt.savefig(output_path, dpi=120)
    plt.close()
    print(f"[SUCCESS] Saved graphical dashboard representation -> {output_path}")


def main():
    print("[INIT] Starting Processing Framework Analysis Core Engine...")
    
    # Secure storage directory architecture
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Gather log footprints matching the pattern
    search_pattern = os.path.join(INPUT_DIR, "stats_*.csv")
    csv_files = glob.glob(search_pattern)

    # Fallback to local root directory search if target execution context varies
    if not csv_files:
        print(f"[INFO] Did not locate file structures within '{INPUT_DIR}/'. Auditing current runtime root directory...")
        csv_files = glob.glob("stats_*.csv")

    if not csv_files:
        print("[ERR] Zero data tracking matrices found matching 'stats_*.csv'. Terminating execution pipeline.")
        return

    print(f"[INFO] Identified {len(csv_files)} individual session file matrices to parse.")
    
    all_sessions_pool = []

    # Iterate over individual files to produce granular reporting profiles
    for filepath in sorted(csv_files):
        filename = os.path.basename(filepath)
        print(f"\n[PARSING] Executing extraction metrics from profile: {filename}")
        
        try:
            df = pd.read_csv(filepath)
            if df.empty:
                continue
                
            all_sessions_pool.append(df)
            
            # Print console summary statistics as required
            print(f"--- Session Stats Details ({filename}) ---")
            print(df['ore_type'].value_counts().reindex(ORE_TYPES, fill_value=0).to_string())
            print(f"-------------------------------------------")
            
            # Generate the dashboard file for this individual log
            dashboard_name = filename.replace(".csv", "_dashboard.png")
            generate_dashboard(df, f"Individual Session File: {filename}", dashboard_name)
            
        except Exception as e:
            print(f"[ERR] Failed compilation mapping sequence across track target {filename}: {e}")

    # Generate the global combined analytics profile
    if all_sessions_pool:
        print("\n" + "="*60)
        print("[COMPILATION] Creating Aggregated Universal Performance Profile...")
        print("="*60)
        
        global_df = pd.concat(all_sessions_pool, ignore_index=True)
        
        print("\n--- Consolidated Universal Statistics ---")
        print(global_df['ore_type'].value_counts().reindex(ORE_TYPES, fill_value=0).to_string())
        print(f"Total Combined Entries Logged: {len(global_df)}")
        print("-------------------------------------------\n")
        
        generate_dashboard(global_df, "Universal Combined Aggregated Global Logs Profile", "global_performance_dashboard.png")
        print("\n[COMPLETE] All data visualization pipelines processed successfully.")


if __name__ == "__main__":
    main()