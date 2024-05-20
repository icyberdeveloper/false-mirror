import tvdb_v4_official


def get_info():
    tvdb = tvdb_v4_official.TVDB('62ec625e-c313-4276-aebb-a847002a07fc')
    res = tvdb.search('Jujutsu Kaisen')
    print(res)


get_info()