# 3Dモデル横断検索

Polyfork、Sand3D、ABO（Amazon Berkeley Objects）の3Dモデルを、名前とカテゴリで横断検索できるページです。一覧モードと、スワイプで選ぶカードモードがあります。

公開ページ: https://oosawak.github.io/3d-model-search/

## 収録データ

- **Polyfork**（全2,791件）: ローポリモデル。GLB／.mjs。ライセンスはモデルごとに CC BY 4.0 または Polyfork ライセンス
- **Sand3D**（サンプル1,000件）: Python コードで表現された3Dモデル（Hugging Face の5データセットから）。索引分は全件 CC BY 4.0
- **ABO**（全7,953件）: Amazon Berkeley Objects。glTF。CC BY 4.0

索引（index.json）は各出所のメタデータとリンク・サムネイルURLだけを保持し、モデルファイル自体は保持しません。各カードに出所・ライセンス・帰属を表示しています。

## 索引の作り直し

```sh
python3 build_index.py
```

Polyfork は `~/workspace/polyfork-catalog` の fork の catalog.json を読みます。
ABO のメタデータ（listings 等）は `abo/` に別途取得したものを使います（このリポには含めていません）。
