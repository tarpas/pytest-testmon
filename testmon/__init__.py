
def merge_db():
    import argparse
    from testmon.db import DB, merge_dbs

    parser = argparse.ArgumentParser()
    parser.add_argument('dbs', metavar='N', type=str, nargs='+')
    parser.add_argument('--output', metavar='N', type=str, nargs='?', default="merged")
    parser.add_argument('--environment', metavar='N', type=str, nargs='?', default="default")

    args = parser.parse_args()
    databases = args.dbs
    output_db = args.output
    env = args.environment

    db_1 = DB(datafile=databases[0], environment=env)
    db_2 = DB(datafile=databases[1], environment=env)
    merge_dbs(merged_datafile=output_db, db_1=db_1, db_2=db_2)
