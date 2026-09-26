import math
import time

def test_hex_binning():
    min_lat = 51.2
    max_lat = 56.3
    min_lon = 23.1
    max_lon = 32.8
    hex_radius_km = 16.0
    
    r_lat = hex_radius_km / 111.3
    r_lon = hex_radius_km / (111.3 * math.cos(math.radians(53.8)))
    col_step = math.sqrt(3) * r_lon
    row_step = 1.5 * r_lat

    # Create dummy 10,000 points across Belarus
    points = [
        {"lat": 51.5 + (i * 0.0004) % 4.5, "lon": 23.5 + (i * 0.0007) % 8.5, "group": i % 3}
        for i in range(10000)
    ]

    t0 = time.time()
    
    # Binning dictionary: (row, col) -> counts
    hex_bins = {}
    
    for p in points:
        lat = p["lat"]
        lon = p["lon"]
        grp = p["group"]
        
        # Estimate row
        approx_row = int(round((max_lat - lat) / row_step))
        
        # Check candidate rows (approx_row - 1, approx_row, approx_row + 1)
        best_dist_sq = 1e9
        best_rc = None
        
        for r in (approx_row - 1, approx_row, approx_row + 1):
            offset = (col_step / 2.0) if (r % 2 == 1) else 0.0
            approx_col = int(round((lon - min_lon - offset) / col_step))
            for c in (approx_col - 1, approx_col, approx_col + 1):
                c_lat = max_lat - r * row_step
                c_lon = min_lon + offset + c * col_step
                
                # Normalized distance to center
                d_lat = (lat - c_lat) / r_lat
                d_lon = (lon - c_lon) / r_lon
                dist_sq = d_lat * d_lat + d_lon * d_lon
                if dist_sq < best_dist_sq:
                    best_dist_sq = dist_sq
                    best_rc = (r, c)
                    
        if best_rc and best_dist_sq <= 1.05: # within hex radius
            b = hex_bins.setdefault(best_rc, {})
            b[grp] = b.get(grp, 0) + 1
            b["total"] = b.get("total", 0) + 1

    elapsed = time.time() - t0
    print(f"Binned 10,000 points into {len(hex_bins)} hexagons in {elapsed*1000:.2f} ms!")
    sample = list(hex_bins.items())[0]
    print(f"Sample bin {sample[0]}: {sample[1]}")

test_hex_binning()
