"""The 60 player-seasons behind build_chart.py, snapshotted from BigQuery.

Columns: season, rank, player, team, games, half_ppr, ppg, yprr, routes,
targets, rec_yards.

PROVENANCE: query.sql, run against yprr_proxy after the 2026-09-18 rebuild.
Regular season only (season_type = 'REG'), and every routes figure is an
actual count of on-field dropbacks -- routes_method is participation_on_field
for all five seasons.

An earlier version of this file carried snap-share ESTIMATES instead, which
ran ~7% off the count at the median and further on some players. The routes
column moved by up to 56 on a single player-season when it was replaced, so
do not compare a yprr here against one taken from an older copy.

To refresh: re-run query.sql, replace ROWS, and RECOMPUTE THE FIT DICT in
build_chart.py in the same pass. FIT holds per-season least-squares slopes,
intercepts and Pearson r fitted to these exact rows; new points under old fit
lines render a chart that looks correct and is not.
"""

ROWS = [
(2021,1,"Cooper Kupp","LA",17,367.0,21.59,3.105,627,191,1947),
(2021,2,"Deebo Samuel Sr.","SF",16,300.5,18.78,3.054,460,121,1405),
(2021,3,"Davante Adams","GB",16,282.8,17.68,2.908,534,169,1553),
(2021,4,"Justin Jefferson","MIN",17,276.4,16.26,2.645,611,167,1616),
(2021,5,"Ja'Marr Chase","CIN",17,264.1,15.54,2.598,560,128,1455),
(2021,6,"Tyreek Hill","KC",17,241.0,14.18,2.241,553,159,1239),
(2021,7,"Stefon Diggs","BUF",17,234.0,13.76,2.038,601,164,1225),
(2021,8,"Mike Evans","TB",16,225.5,14.09,1.664,622,114,1035),
(2021,9,"Diontae Johnson","PIT",16,220.9,13.81,1.888,615,169,1161),
(2021,10,"Mike Williams","LAC",16,208.6,13.04,2.050,559,129,1146),
(2021,11,"Hunter Renfrow","LV",17,207.6,12.21,1.977,525,128,1038),
(2021,12,"DK Metcalf","SEA",17,206.8,12.16,2.036,475,129,967),
(2022,1,"Justin Jefferson","MIN",17,304.7,17.92,2.645,684,184,1809),
(2022,2,"Davante Adams","LV",17,285.5,16.79,2.544,596,180,1516),
(2022,3,"Tyreek Hill","MIA",17,281.7,16.57,3.295,519,170,1710),
(2022,4,"Stefon Diggs","BUF",16,262.6,16.41,2.727,524,154,1429),
(2022,5,"A.J. Brown","PHI",17,255.6,15.04,2.786,537,145,1496),
(2022,6,"CeeDee Lamb","DAL",17,248.1,14.59,2.453,554,156,1359),
(2022,7,"Jaylen Waddle","MIA",17,221.7,13.04,2.659,510,117,1356),
(2022,8,"Amon-Ra St. Brown","DET",16,214.6,13.41,2.465,471,146,1161),
(2022,9,"DeVonta Smith","PHI",17,209.1,12.30,2.136,560,136,1196),
(2022,10,"Amari Cooper","CLE",17,207.0,12.18,2.180,532,132,1160),
(2022,11,"Christian Kirk","JAX",17,199.9,11.76,1.837,603,133,1108),
(2022,12,"Ja'Marr Chase","CIN",12,198.9,16.57,2.092,500,134,1046),
(2023,1,"CeeDee Lamb","DAL",17,335.7,19.75,2.920,599,181,1749),
(2023,2,"Tyreek Hill","MIA",16,316.9,19.81,3.945,456,171,1799),
(2023,3,"Amon-Ra St. Brown","DET",16,271.4,16.96,2.630,576,164,1515),
(2023,4,"Puka Nacua","LA",17,246.0,14.47,2.635,564,160,1486),
(2023,5,"Mike Evans","TB",17,243.0,14.29,2.432,516,136,1255),
(2023,6,"DJ Moore","CHI",17,238.5,14.03,2.521,541,136,1364),
(2023,7,"A.J. Brown","PHI",17,236.6,13.92,2.721,535,158,1456),
(2023,8,"Keenan Allen","LAC",13,224.9,17.30,2.501,497,150,1243),
(2023,9,"Nico Collins","HOU",15,220.4,14.69,3.187,407,109,1297),
(2023,10,"Stefon Diggs","BUF",17,220.3,12.96,2.151,550,160,1183),
(2023,11,"Davante Adams","LV",17,213.9,12.58,2.007,570,175,1144),
(2023,12,"Deebo Samuel Sr.","SF",15,213.7,14.25,2.404,371,89,892),
(2024,1,"Ja'Marr Chase","CIN",17,339.5,19.97,2.490,686,175,1708),
(2024,2,"Justin Jefferson","MIN",17,266.0,15.65,2.621,585,154,1533),
(2024,3,"Amon-Ra St. Brown","DET",17,258.7,15.22,2.343,539,141,1263),
(2024,4,"Brian Thomas Jr.","JAX",17,240.5,14.15,2.544,504,133,1282),
(2024,5,"Drake London","ATL",17,230.8,13.58,2.319,548,158,1271),
(2024,6,"Terry McLaurin","WAS",17,226.8,13.34,2.264,484,117,1096),
(2024,7,"Malik Nabers","NYG",15,219.1,14.61,2.250,535,170,1204),
(2024,8,"CeeDee Lamb","DAL",15,212.9,14.19,2.314,516,152,1194),
(2024,9,"Mike Evans","TB",14,203.4,14.53,2.608,385,110,1004),
(2024,10,"Jaxon Smith-Njigba","SEA",17,203.0,11.94,1.865,606,137,1130),
(2024,11,"Garrett Wilson","NYJ",17,201.4,11.85,1.733,637,154,1104),
(2024,12,"Ladd McConkey","LAC",16,199.9,12.49,2.520,456,112,1149),
(2025,1,"Puka Nacua","LA",16,310.5,19.41,3.688,465,166,1715),
(2025,2,"Jaxon Smith-Njigba","SEA",17,300.4,17.67,3.767,476,163,1793),
(2025,3,"Amon-Ra St. Brown","DET",17,265.5,15.62,2.484,564,172,1401),
(2025,4,"Ja'Marr Chase","CIN",16,251.1,15.69,2.281,619,185,1412),
(2025,5,"George Pickens","DAL",17,245.4,14.44,2.434,587,137,1429),
(2025,6,"Chris Olave","NO",16,218.0,13.62,2.084,558,156,1163),
(2025,7,"Zay Flowers","BAL",17,200.3,11.78,2.715,446,118,1211),
(2025,8,"Davante Adams","LA",14,192.9,13.78,1.934,408,114,789),
(2025,9,"Nico Collins","HOU",15,190.7,12.71,2.439,458,120,1117),
(2025,10,"Jameson Williams","DET",17,187.4,11.02,1.884,593,102,1117),
(2025,11,"Courtland Sutton","DEN",17,182.7,10.75,1.721,591,124,1017),
(2025,12,"Tee Higgins","CIN",15,182.1,12.14,1.630,519,98,846),
]
