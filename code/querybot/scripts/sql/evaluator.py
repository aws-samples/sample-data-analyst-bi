from scripts.sql.executor import get_database_helper
from pandas.io.sql import DatabaseError
import pandas as pd

def measure_exact_match(pred_sqls: list[str], gt_sqls: list[str]) -> list[int]:

    assert len(pred_sqls) == len(gt_sqls), "Mismatch between predicted and GT SQL counts!"
    em = []
    for pred, gt in zip(pred_sqls, gt_sqls):
        pred_tokens = pred.lower().split()
        gt_tokens = gt.lower().split()
        em.append(1 if pred_tokens == gt_tokens else 0)
    return em


def measure_execution_match(pred_sqls: list[str], gt_sqls: list[str], db_type, 
                             database: str, db_conn_conf: dict[str, str], schema: str) -> list[int]:

    assert len(pred_sqls) == len(gt_sqls), "Mismatch between predicted and GT SQL counts!"
    db_helper = get_database_helper(db_type,
                                    db_conn_conf,
                                    None,
                                    None,
                                    None,
                                    0,
                                    schema_file=schema)
    def compare_results(df_pred, df_gt):
        gt_cols_matched = []
        pred_cols = sorted(df_pred.columns)
        gt_cols = sorted(df_gt.columns)
        for gc in gt_cols:
            gv = df_gt[gc].values
            for pc in pred_cols:
                pv = df_pred[pc].values
                if sorted(gv) == sorted(pv):
                    gt_cols_matched.append(gc)
                    pred_cols.remove(pc)
                    break
        return gt_cols_matched

    em = []
    for pred, gt in zip(pred_sqls, gt_sqls):
        try:
            df_pred, _ = db_helper.run_sql(None, pred)
            df_gt, _ = db_helper.run_sql(None, gt)
        except DatabaseError as e:
            print (e)
            em.append(0)
            continue

        if len(df_pred) != len(df_gt) or df_pred.shape != df_gt.shape:
            em.append(0)
            continue

        gt_cols_matched = compare_results(df_pred, df_gt)
        em.append(1 if len(gt_cols_matched) == df_gt.shape[1] else 0)

    return em
