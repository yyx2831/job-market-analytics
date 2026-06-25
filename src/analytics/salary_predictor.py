"""薪资预测模型 — 基于城市/经验/学历/技能/行业/公司规模预测月薪。

使用多模型集成：线性回归 (benchmark) + 随机森林 (主模型) + XGBoost (如果可用)

用法:
  from src.analytics.salary_predictor import SalaryPredictor
  pred = SalaryPredictor()
  pred.train(jobs_df)
  salary = pred.predict(city="成都", experience="3年及以上", education="本科", skills=["Python","LLM"])
  pred.report()
"""

from __future__ import annotations

import pickle
from typing import Optional, Any
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from sklearn.impute import SimpleImputer


class SalaryPredictor:
    """薪资预测器 — 多特征 → 月薪 (元)"""

    # 城市薪资基准 (从数据中学到的先验)
    CITY_BASELINE = {
        "杭州": 1.15, "北京": 1.10, "上海": 1.10, "深圳": 1.05,
        "广州": 1.00, "成都": 1.00, "武汉": 0.95, "南京": 0.95,
        "西安": 0.88, "重庆": 0.88, "长沙": 0.85, "苏州": 0.92,
        "天津": 0.90, "合肥": 0.85,
    }

    # 经验级别倍率
    EXPERIENCE_MULTIPLIER = {
        "无需经验": 0.60, "1年及以上": 0.75, "1-3年": 0.85,
        "2年及以上": 0.90, "2-5年": 0.95, "3年及以上": 1.00,
        "3-5年": 1.05, "3-10年": 1.10, "5年及以上": 1.15,
        "5-10年": 1.20, "8年及以上": 1.35, "10年及以上": 1.50,
    }

    # 学历倍率
    EDUCATION_MULTIPLIER = {
        "高中": 0.60, "中技/中专": 0.65, "大专": 0.85,
        "本科": 1.00, "硕士": 1.20, "博士": 1.50,
    }

    def __init__(self):
        self.model = None
        self.preprocessor = None
        self.feature_names: list[str] = []
        self.rf_importance: dict[str, float] = {}
        self.metrics: dict[str, float] = {}
        self.skills_coefficients: dict[str, float] = {}
        self.is_trained = False

    def _extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """从 DataFrame 提取特征矩阵"""
        X = pd.DataFrame(index=df.index)

        # 1. 城市编码 (one-hot 后处理)
        X["city"] = df["city"].fillna("未知")

        # 2. 经验编码为倍率
        X["experience_mult"] = df["experience"].map(self.EXPERIENCE_MULTIPLIER).fillna(1.0)

        # 3. 学历编码为倍率
        X["education_mult"] = df["education"].map(self.EDUCATION_MULTIPLIER).fillna(1.0)

        # 4. 技能数量
        X["skill_count"] = df["skills"].apply(
            lambda s: len([x.strip() for x in str(s).split(",") if x.strip()]) if pd.notna(s) else 0
        )

        # 5. 公司规模编码 (越大越好)
        size_map = {
            "少于15人": 0.8, "15-50人": 0.85, "50-150人": 0.90,
            "150-500人": 1.0, "500-1000人": 1.10, "1000-5000人": 1.15,
            "5000-10000人": 1.25, "10000人以上": 1.35,
        }
        X["company_size_mult"] = df["company_size"].map(size_map).fillna(1.0)

        # 6. 行业编码 (高频行业)
        top_industries = [
            "计算机软件", "互联网", "通信", "电子技术", "金融", "医疗",
            "汽车", "机械", "教育", "房地产",
        ]
        for ind in top_industries:
            X[f"industry_{ind}"] = df["industry"].fillna("").str.contains(ind, regex=False).astype(int)

        # 7. is_active
        X["is_active"] = df.get("is_active", pd.Series([1] * len(df))).fillna(1)

        return X

    def feat_engineering(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """
        特征工程 → numpy arrays。

        返回:
          X: 特征矩阵
          y: 目标变量 (salary_avg)
        """
        # 先过滤有薪资的
        df = df[df["salary_avg"].notna() & (df["salary_avg"] > 0)].copy()
        df = df[df["salary_unit"].isin(["month"]) | df["salary_unit"].isna()].copy()

        X = self._extract_features(df)
        y = df["salary_avg"].values  # 元/月

        # 删除 city 列 (后面 one-hot)
        city_series = X.pop("city")

        # 将 city 转为 one-hot
        try:
            city_encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
            city_onehot = city_encoder.fit_transform(city_series.values.reshape(-1, 1))
            city_cols = [f"city_{c}" for c in city_encoder.categories_[0]]
        except Exception:
            city_onehot = np.zeros((len(X), 1))
            city_cols = ["city_未知"]

        # 合并
        X_numeric = X.values.astype(np.float64)
        self.feature_names = list(X.columns) + city_cols

        # Impute NaN
        X_numeric = np.nan_to_num(X_numeric, nan=0.0)

        return np.hstack([X_numeric, city_onehot]), y

    def train(self, df: pd.DataFrame) -> dict[str, float]:
        """训练模型并返回评估指标"""
        X, y = self.feat_engineering(df)
        print(f"   训练样本: {len(y)} 条, 特征维度: {X.shape[1]}")

        # 划分
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # 标准化
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # ── 模型 1: Linear Regression (benchmark) ──
        lr = LinearRegression()
        lr.fit(X_train_scaled, y_train)
        lr_pred = lr.predict(X_test_scaled)
        lr_r2 = r2_score(y_test, lr_pred)
        lr_mae = mean_absolute_error(y_test, lr_pred)

        # ── 模型 2: Random Forest (主模型) ──
        rf = RandomForestRegressor(
            n_estimators=200, max_depth=15, min_samples_leaf=5,
            random_state=42, n_jobs=-1,
        )
        rf.fit(X_train_scaled, y_train)
        rf_pred = rf.predict(X_test_scaled)
        rf_r2 = r2_score(y_test, rf_pred)
        rf_mae = mean_absolute_error(y_test, rf_pred)

        # ── 模型 3: Gradient Boosting ──
        gb = GradientBoostingRegressor(
            n_estimators=100, max_depth=6, min_samples_leaf=5,
            random_state=42,
        )
        gb.fit(X_train_scaled, y_train)
        gb_pred = gb.predict(X_test_scaled)
        gb_r2 = r2_score(y_test, gb_pred)
        gb_mae = mean_absolute_error(y_test, gb_pred)

        # 选最佳
        models = {"Linear": (lr, lr_r2), "RandomForest": (rf, rf_r2), "GradientBoost": (gb, gb_r2)}
        best_name = max(models, key=lambda k: models[k][1])
        self.model = models[best_name][0]
        self.scaler = scaler
        self.is_trained = True

        # 特征重要性
        if best_name == "RandomForest":
            importances = self.model.feature_importances_
            self.rf_importance = {
                self.feature_names[i]: float(importances[i])
                for i in np.argsort(-importances)[:20]
            }

        self.metrics = {
            "model": best_name,
            "lr_r2": round(lr_r2, 4), "lr_mae": round(lr_mae, 0),
            "rf_r2": round(rf_r2, 4), "rf_mae": round(rf_mae, 0),
            "gb_r2": round(gb_r2, 4), "gb_mae": round(gb_mae, 0),
            "samples": len(y),
            "features": X.shape[1],
        }
        return self.metrics

    def predict(
        self,
        city: str = "成都",
        experience: str = "3年及以上",
        education: str = "本科",
        skills: Optional[list[str]] = None,
        company_size: str = "150-500人",
        industry: str = "计算机软件",
        is_active: int = 1,
    ) -> dict[str, Any]:
        """预测给定配置的薪资"""
        if not self.is_trained:
            return {"error": "模型未训练", "prediction": None}

        skills = skills or []
        df = pd.DataFrame([{
            "city": city,
            "experience": experience,
            "education": education,
            "skills": ",".join(skills),
            "company_size": company_size,
            "industry": industry,
            "is_active": is_active,
        }])

        X_df = self._extract_features(df)
        city_series = X_df.pop("city")

        # One-hot encode city matching training cols
        city_onehot = np.zeros((1, len([c for c in self.feature_names if c.startswith("city_")])))
        city_name = city or "未知"
        for i, feat in enumerate(self.feature_names):
            if feat.startswith("city_") and feat == f"city_{city_name}":
                city_onehot[0, i - (len(self.feature_names) - len(city_onehot[0]))] = 1

        X_numeric = X_df.values.astype(np.float64)
        X_numeric = np.nan_to_num(X_numeric, nan=0.0)
        X = np.hstack([X_numeric, city_onehot])

        # Pad to match training feature count
        if X.shape[1] < len(self.feature_names):
            pad = np.zeros((1, len(self.feature_names) - X.shape[1]))
            X = np.hstack([X, pad])
        elif X.shape[1] > len(self.feature_names):
            X = X[:, :len(self.feature_names)]

        X_scaled = self.scaler.transform(X)
        salary = float(self.model.predict(X_scaled)[0])
        salary_k = round(salary / 1000, 1)

        return {
            "prediction": int(salary),
            "salary_k": salary_k,
            "monthly": f"¥{salary_k}K/月",
            "annual": f"¥{salary_k * 12 / 10:.1f}万/年",
            "annual_15": f"¥{salary_k * 15 / 10:.1f}万/年(15薪)",  # 假设15薪
        }

    def predict_batch(
        self, df: pd.DataFrame, salary_months: int = 12
    ) -> pd.DataFrame:
        """批量预测"""
        if not self.is_trained:
            raise RuntimeError("模型未训练")

        X, _ = self.feat_engineering(df)

        # Pad
        if X.shape[1] < len(self.feature_names):
            pad = np.zeros((X.shape[0], len(self.feature_names) - X.shape[1]))
            X = np.hstack([X, pad])
        elif X.shape[1] > len(self.feature_names):
            X = X[:, :len(self.feature_names)]

        X_scaled = self.scaler.transform(X)
        preds = self.model.predict(X_scaled)

        result = df.copy()
        result["predicted_salary"] = preds.astype(int)
        result["predicted_annual"] = (preds * salary_months).astype(int)
        return result

    def report(self) -> str:
        """生成模型报告"""
        if not self.is_trained:
            return "模型未训练"

        lines = [
            f"## 薪资预测模型报告",
            f"",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 模型 | {self.metrics.get('model', '?')} |",
            f"| 训练样本 | {self.metrics.get('samples', '?')} 条 |",
            f"| 特征维度 | {self.metrics.get('features', '?')} |",
            f"| R² | {self.metrics.get('rf_r2', '?')} (RF), {self.metrics.get('gb_r2', '?')} (GB) |",
            f"| MAE (月薪) | ¥{self.metrics.get('rf_mae', '?'):.0f} |",
            f"",
            f"### TOP 特征重要性",
            f"",
            f"| 排名 | 特征 | 重要性 |",
            f"|------|------|--------|",
        ]
        for i, (k, v) in enumerate(list(self.rf_importance.items())[:10]):
            lines.append(f"| {i+1} | {k} | {v:.4f} |")

        return "\n".join(lines)

    def save(self, path: str) -> None:
        """保存模型到文件"""
        import pickle
        with open(path, "wb") as f:
            pickle.dump({
                "model": self.model,
                "scaler": self.scaler,
                "feature_names": self.feature_names,
                "rf_importance": self.rf_importance,
                "metrics": self.metrics,
            }, f)

    @classmethod
    def load(cls, path: str) -> "SalaryPredictor":
        """从文件加载模型"""
        import pickle
        with open(path, "rb") as f:
            data = pickle.load(f)
        pred = cls()
        pred.model = data["model"]
        pred.scaler = data["scaler"]
        pred.feature_names = data["feature_names"]
        pred.rf_importance = data["rf_importance"]
        pred.metrics = data["metrics"]
        pred.is_trained = True
        return pred
