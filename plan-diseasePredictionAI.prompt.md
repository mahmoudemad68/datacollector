## Plan: 1M Medical Dataset Pipeline

بناء pipeline بلغة Python (Pandas/Polars) مع MongoDB كمخزن أساسي لإنتاج 1,000,000 سجل طبي خلال أسبوع، عبر دمج بيانات حقيقية متعددة المصادر مع توليد بيانات تركيبية مضبوطة (<=70%). النهج المقترح: تأسيس طبقة ingestion موحدة لكل مصدر، ثم توحيد الـ schema، ثم enrichment (treatment/drugs/probability/urgency)، ثم generator للتراكيب الواقعية مع قواعد طبية، ثم validation صارم وجودة نهائية قبل التصدير.

**Steps**
1. Phase 1 - Bootstrap (Day 1): تهيئة المشروع والاعتماديات وبنية المجلدات الأساسية (`config`, `sources`, `processors`, `pipeline`, `storage`, `data_quality`) وتعريف إعدادات التشغيل (API keys, rate limit, batch size, retries). هذا يمهد لكل الخطوات اللاحقة.
2. Phase 2 - Canonical Schema & Contracts (Day 1, depends on 1): تصميم schema موحّد للصف الطبي (symptoms list, disease_id/name, age_group, gender, probability, treatment, drugs, urgency, source provenance, confidence, timestamps) مع توثيق أنواع الحقول والقيم المسموحة وسياسة null-handling.
3. Phase 3 - Disease Base Ingestion (Day 2, depends on 2): بناء connectors لـ WHO ICD و UMLS لاستخراج الأمراض مع deduplication وnormalization (synonyms/aliases) للحصول على disease master table مستهدفة ~10k مرض نظيف.
4. Phase 4 - Symptom Mapping (Day 2-3, depends on 3): إدخال SymCAT + Human Disease Symptom Network + Infermedica وربط disease-symptom بعلاقات weighted؛ توحيد الأعراض في قاموس symptom ontology وتقليل التكرار اللغوي/المرادفات.
5. Phase 5 - Treatment & Drugs Enrichment (Day 3-4, parallel with 4 after 3): دمج MedlinePlus + openFDA + ClinicalTrials لتعبئة treatment/drugs وربطها بكل disease مع source confidence وتحديد مستوى الثقة عند تعارض المصادر.
6. Phase 6 - Probability & Urgency Modeling (Day 4, depends on 4 and 5): احتساب probability لكل علاقة مرض-عرض من SymCAT/Infermedica أو fallback heuristic، ثم اشتقاق urgency (low/medium/high/emergency) بقواعد واضحة تعتمد على disease severity + symptom clusters.
7. Phase 7 - Synthetic Combination Generator (Day 4-5, depends on 6): توليد تراكيب أعراض واقعية لكل مرض بقيود طبية (حد أدنى/أقصى للأعراض، co-occurrence plausibility، استبعاد التركيبات الشاذة)، مع cap للبيانات التركيبية <=70% ووسم واضح `is_synthetic`.
8. Phase 8 - Dataset Builder to 1M (Day 5-6, depends on 7): بناء batches حتى 1,000,000 سجل، توزيع متوازن نسبيًا عبر الأمراض والفئات العمرية والجنس، إدراج provenance per row، وتخزين مرحلي في MongoDB (collections: diseases, symptoms, relations, final_rows).
9. Phase 9 - Data Quality Gate (Day 6, depends on 8): تطبيق قواعد جودة إلزامية (uniqueness, schema validation, probability range [0,1], required fields completeness, leakage checks, class imbalance thresholds) مع تقرير جودة رقمي.
10. Phase 10 - Export & Handoff (Day 7, depends on 9): تصدير نسخ تدريبية (Mongo snapshot + optional parquet extract)، توثيق data dictionary، توثيق القيود ومصادر البيانات ونسب real/synthetic، وإعداد ready-to-train split.

**Relevant files**
- `/home/mahmoud/Desktop/datacollector/main.py` — نقطة orchestration لتشغيل مراحل pipeline ومهام CLI.
- `/home/mahmoud/Desktop/datacollector/config/settings.py` — إعدادات API keys, retries, rate limits, batch/window sizes.
- `/home/mahmoud/Desktop/datacollector/config/schema.py` — تعريف canonical schema والتحقق من الأنواع والقيم.
- `/home/mahmoud/Desktop/datacollector/sources/base.py` — واجهة موحدة لـ connectors (fetch, normalize, paginate, checkpoint).
- `/home/mahmoud/Desktop/datacollector/sources/icd_connector.py` — ingestion لأمراض WHO ICD.
- `/home/mahmoud/Desktop/datacollector/sources/umls_connector.py` — ingestion لأمراض UMLS + synonyms.
- `/home/mahmoud/Desktop/datacollector/sources/symptom_connectors.py` — ingestion لعلاقات المرض-العرض من SymCAT/Infermedica/HDSN.
- `/home/mahmoud/Desktop/datacollector/sources/treatment_connectors.py` — enrichment من MedlinePlus/openFDA/ClinicalTrials.
- `/home/mahmoud/Desktop/datacollector/processors/normalization.py` — توحيد النصوص/المرادفات/القيم.
- `/home/mahmoud/Desktop/datacollector/processors/probability_engine.py` — حساب probability ودمج أوزان المصادر.
- `/home/mahmoud/Desktop/datacollector/processors/urgency_rules.py` — قواعد urgency القابلة للمراجعة.
- `/home/mahmoud/Desktop/datacollector/processors/synthetic_generator.py` — توليد التركيبات الواقعية مع قيود طبية.
- `/home/mahmoud/Desktop/datacollector/storage/mongo_store.py` — عمليات الإدخال/الفهرسة/الـ upsert في MongoDB.
- `/home/mahmoud/Desktop/datacollector/pipeline/build_dataset.py` — التجميع النهائي للـ 1M rows.
- `/home/mahmoud/Desktop/datacollector/data_quality/validators.py` — اختبارات الجودة الإلزامية.
- `/home/mahmoud/Desktop/datacollector/README.md` — التوثيق التشغيلي ومخطط التشغيل.

**Verification**
1. تشغيل smoke test لكل connector على عينة صغيرة والتأكد من نجاح pagination/retry وحدود rate-limit.
2. تنفيذ schema validation على 10k صف أولية مع نسبة أخطاء <1% قبل التوسعة.
3. فحص deduplication: معدل التكرار في disease names وsymptom labels أقل من threshold متفق عليه.
4. اختبار توزيع البيانات: تقرير يوضح توازن الأمراض والفئات العمرية والجنس ونسبة synthetic <=70%.
5. اختبار sanity إحصائي: probability داخل [0,1]، وعدم وجود urgency فارغ، وعدم وجود rows بلا disease.
6. تشغيل build كامل على 100k كمرحلة pre-production ثم run نهائي إلى 1M مع checkpoints.
7. التحقق من الجاهزية للتدريب: استخراج split (train/valid/test) بدون data leakage على مستوى disease-symptom pair الحساسة.

**Decisions**
- التنفيذ المعتمد: Python + Pandas/Polars.
- التخزين الأساسي: MongoDB.
- السقف الأعلى للبيانات التركيبية: 70%.
- الاستخدام: بحثي فقط، مع قبول مصادر قد تكون مقيدة لإعادة التوزيع التجاري.
- الهدف الزمني: MVP خلال أسبوع.
- ضمن النطاق: جمع/توحيد/إثراء/توليد/تحقق/تصدير dataset.
- خارج النطاق الحالي: تدريب النماذج وتقييمها السريري النهائي والإطلاق الإنتاجي.

**Further Considerations**
1. سياسة التوازن: التوصية عدم فرض توازن كامل لكل الأمراض؛ اعتماد floor/ceiling per disease لتجنب تضخيم أمراض نادرة بشكل مصطنع.
2. سياسة provenance: التوصية بإلزام `source_list` و`confidence_score` لكل صف لسهولة التدقيق لاحقًا.
3. سياسة الجودة الطبية: التوصية بمراجعة عينة 500-1000 صف يدويًا من مختص صحي قبل التدريب.