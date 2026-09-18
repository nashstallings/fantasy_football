"""The 60 player-seasons behind build_chart.py, snapshotted from BigQuery.

Columns: season, rank, player, team, games, half_ppr, ppg, yprr, routes,
targets, rec_yards.

PROVENANCE, and why the yprr column is stale:

Regular season only -- that part is right, and predates the fix, because the
query that produced these rows reimplemented the routes denominator in SQL
specifically to avoid yprr_proxy's pooling.

But the routes are snap-share ESTIMATES (offense_snap_pct * team_dropbacks),
not counts. The estimate runs about 7% off the exact on-field count at the
median and much further on some players: Nacua's 2025 row says 409 routes and
4.193 YPRR where the count is 465 and 3.688. Every yprr value here is off by
some amount in that range.

Refresh from query.sql once the nfl_data pipeline has been re-run -- it now
reads the corrected table directly. The per-season FIT constants in
build_chart.py are regressions over these rows and must be recomputed at the
same time.
"""

ROWS = [
(2021,1,"Cooper Kupp","LA",17,367.0,21.59,3.232,602,191,1947),
(2021,2,"Deebo Samuel Sr.","SF",16,300.5,18.78,3.357,419,121,1405),
(2021,3,"Davante Adams","GB",16,282.8,17.68,3.112,499,169,1553),
(2021,4,"Justin Jefferson","MIN",17,276.4,16.26,2.855,566,167,1616),
(2021,5,"Ja'Marr Chase","CIN",17,264.1,15.54,2.787,522,128,1455),
(2021,6,"Tyreek Hill","KC",17,241.0,14.18,2.410,514,159,1239),
(2021,7,"Stefon Diggs","BUF",17,234.0,13.76,2.188,560,164,1225),
(2021,8,"Mike Evans","TB",16,225.5,14.09,1.751,591,114,1035),
(2021,9,"Diontae Johnson","PIT",16,220.9,13.81,2.002,580,169,1161),
(2021,10,"Mike Williams","LAC",16,208.6,13.04,2.187,524,129,1146),
(2021,11,"Hunter Renfrow","LV",17,207.6,12.21,2.303,451,128,1038),
(2021,12,"DK Metcalf","SEA",17,206.8,12.16,2.141,452,129,967),
(2022,1,"Justin Jefferson","MIN",17,304.7,17.92,2.706,668,184,1809),
(2022,2,"Davante Adams","LV",17,285.5,16.79,2.587,586,180,1516),
(2022,3,"Tyreek Hill","MIA",17,281.7,16.57,3.637,470,170,1710),
(2022,4,"Stefon Diggs","BUF",16,262.6,16.41,3.051,468,154,1429),
(2022,5,"A.J. Brown","PHI",17,255.6,15.04,3.039,492,145,1496),
(2022,6,"CeeDee Lamb","DAL",17,248.1,14.59,2.651,513,156,1359),
(2022,7,"Jaylen Waddle","MIA",17,221.7,13.04,2.965,457,117,1356),
(2022,8,"Amon-Ra St. Brown","DET",16,214.6,13.41,2.612,444,146,1161),
(2022,9,"DeVonta Smith","PHI",17,209.1,12.30,2.243,533,136,1196),
(2022,10,"Amari Cooper","CLE",17,207.0,12.18,2.369,490,132,1160),
(2022,11,"Christian Kirk","JAX",17,199.9,11.76,1.999,554,133,1108),
(2022,12,"Ja'Marr Chase","CIN",12,198.9,16.57,2.206,474,134,1046),
(2023,1,"CeeDee Lamb","DAL",17,335.7,19.75,3.182,550,181,1749),
(2023,2,"Tyreek Hill","MIA",16,316.9,19.81,4.659,386,171,1799),
(2023,3,"Amon-Ra St. Brown","DET",16,271.4,16.96,2.762,549,164,1515),
(2023,4,"Puka Nacua","LA",17,246.0,14.47,2.735,543,160,1486),
(2023,5,"Mike Evans","TB",17,243.0,14.29,2.623,479,136,1255),
(2023,6,"DJ Moore","CHI",17,238.5,14.03,2.676,510,136,1364),
(2023,7,"A.J. Brown","PHI",17,236.6,13.92,2.749,530,158,1456),
(2023,8,"Keenan Allen","LAC",13,224.9,17.30,2.705,460,150,1243),
(2023,9,"Nico Collins","HOU",15,220.4,14.69,3.442,377,109,1297),
(2023,10,"Stefon Diggs","BUF",17,220.3,12.96,2.347,504,160,1183),
(2023,11,"Davante Adams","LV",17,213.9,12.58,2.083,549,175,1144),
(2023,12,"Deebo Samuel Sr.","SF",15,213.7,14.25,2.587,345,89,892),
(2024,1,"Ja'Marr Chase","CIN",17,339.5,19.97,2.622,651,175,1708),
(2024,2,"Justin Jefferson","MIN",17,266.0,15.65,2.745,559,154,1533),
(2024,3,"Amon-Ra St. Brown","DET",17,258.7,15.22,2.448,516,141,1263),
(2024,4,"Brian Thomas Jr.","JAX",17,240.5,14.15,2.783,461,133,1282),
(2024,5,"Drake London","ATL",17,230.8,13.58,2.377,535,158,1271),
(2024,6,"Terry McLaurin","WAS",17,226.8,13.34,2.353,466,117,1096),
(2024,7,"Malik Nabers","NYG",15,219.1,14.61,2.358,511,170,1204),
(2024,8,"CeeDee Lamb","DAL",15,212.9,14.19,2.437,490,152,1194),
(2024,9,"Mike Evans","TB",14,203.4,14.53,2.862,351,110,1004),
(2024,10,"Jaxon Smith-Njigba","SEA",17,203.0,11.94,2.021,559,137,1130),
(2024,11,"Garrett Wilson","NYJ",17,201.4,11.85,1.772,623,153,1104),
(2024,12,"Ladd McConkey","LAC",16,199.9,12.49,2.975,386,112,1149),
(2025,1,"Puka Nacua","LA",16,310.5,19.41,4.193,409,166,1715),
(2025,2,"Jaxon Smith-Njigba","SEA",17,300.4,17.67,4.420,406,163,1793),
(2025,3,"Amon-Ra St. Brown","DET",17,265.5,15.62,2.593,540,172,1401),
(2025,4,"Ja'Marr Chase","CIN",16,251.1,15.69,2.335,605,185,1412),
(2025,5,"George Pickens","DAL",17,245.4,14.44,2.651,539,137,1429),
(2025,6,"Chris Olave","NO",16,218.0,13.63,2.293,507,156,1163),
(2025,7,"Zay Flowers","BAL",17,200.3,11.78,2.981,406,118,1211),
(2025,8,"Davante Adams","LA",14,192.9,13.78,2.252,350,114,789),
(2025,9,"Nico Collins","HOU",15,190.7,12.71,2.684,416,120,1117),
(2025,10,"Jameson Williams","DET",17,187.4,11.02,1.979,564,102,1117),
(2025,11,"Courtland Sutton","DEN",17,182.7,10.75,1.860,547,124,1017),
(2025,12,"Tee Higgins","CIN",15,182.1,12.14,1.773,477,98,846),
]
