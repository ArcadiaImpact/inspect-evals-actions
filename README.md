# Register lint results

Static checks from [inspect-evals-lint](https://github.com/Generality-Labs/inspect-evals-lint) run against each register entry's upstream repository at its pinned commit. Score is passing/applicable checks; warnings pass, suppressed checks do not, skipped checks are not applicable.

| Eval | Status | Score | Structure | Code quality | Tests | Best practices | Commit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ahb | linted | 15/17 | 5/5 | 3/4 | 3/4 | 4/4 | [`4b7b631`](https://github.com/icaro-lab/ahb/tree/4b7b631245fa300df98d2c310e83273ed0d4a207) |
| alignment_faking | linted | 11/15 | 5/5 | 3/3 | 1/4 | 2/3 | [`d102d21`](https://github.com/marliechorgan/alignment-faking-inspect/tree/d102d213833b05c67464a44e28e9a414977f80e1) |
| appworld | linted | 19/19 | 6/6 | 3/3 | 6/6 | 4/4 | [`880fbc4`](https://github.com/anirudhvenu/appworld-inspect/tree/880fbc47e73270576137b928fdb1ecab61529da1) |
| aratrust | linted | 15/15 | 6/6 | 3/3 | 3/3 | 3/3 | [`e4b89df`](https://github.com/Raulster24/aratrust-inspect/tree/e4b89df399057ca5ae8f8524418907c4868badcd) |
| arxivrollbench | unsupported_layout: arxivrollbench_inspect.py is not inside a package (no __init__.py next to it); inspect-evals-lint checks one package per evaluation | - | - | - | - | - | [`01ec6e1`](https://github.com/liangzid/ArxivRoll/tree/01ec6e132e1cccdc204bed8b20a8473bb82c3ca7) |
| bixbench | linted | 12/17 | 4/5 | 3/3 | 2/6 | 3/3 | [`e99597c`](https://github.com/concordia-ai/concordia_evals/tree/e99597c8a5d68c85a5bbbb00020d7d1c813ad0e1) |
| brokenmath | linted | 13/16 | 6/6 | 3/3 | 1/4 | 3/3 | [`d37b80b`](https://github.com/Vedant-Agarwal/inspect-brokenmath/tree/d37b80bb16c9d98df990a7edd92323a1d73822bb) |
| castle | linted | 13/16 | 6/6 | 3/3 | 1/4 | 3/3 | [`dc4d5aa`](https://github.com/AI-Sec-dev/inspect-eval-castle/tree/dc4d5aa275120b6cc7943b54b67e2278c80f6f4c) |
| chipbench_debug | linted | 15/17 | 6/6 | 2/3 | 3/4 | 4/4 | [`8a60e2e`](https://github.com/Plswearpants/Inspect-Eval-ChipBench/tree/8a60e2e8914139c1e73fe62ae8018dc240605ff3) |
| chipbench_refmodel | linted | 15/17 | 6/6 | 2/3 | 3/4 | 4/4 | [`8a60e2e`](https://github.com/Plswearpants/Inspect-Eval-ChipBench/tree/8a60e2e8914139c1e73fe62ae8018dc240605ff3) |
| chipbench_verilog_gen | linted | 15/17 | 6/6 | 2/3 | 3/4 | 4/4 | [`8a60e2e`](https://github.com/Plswearpants/Inspect-Eval-ChipBench/tree/8a60e2e8914139c1e73fe62ae8018dc240605ff3) |
| contractbench | linted | 9/14 | 3/4 | 2/3 | 1/4 | 3/3 | [`22d3910`](https://github.com/SecurityLab-UCD/ContractBench-inspect/tree/22d39108619433a9f7bc8eb3b410bbf384d67616) |
| deceptionbench | linted | 12/16 | 3/4 | 3/3 | 2/5 | 4/4 | [`8683bf5`](https://github.com/WatchTree-19/inspect-deceptionbench/tree/8683bf5a480f938b812aa5078fb0ee7d12a74483) |
| do_not_answer | linted | 16/18 | 6/6 | 3/3 | 3/5 | 4/4 | [`b386689`](https://github.com/mkzung/inspect-evals-do-not-answer/tree/b386689ab2d469ea1ff9eb423ac048549f7542c5) |
| do_not_answer_adversarial | linted | 16/18 | 6/6 | 3/3 | 3/5 | 4/4 | [`b386689`](https://github.com/mkzung/inspect-evals-do-not-answer/tree/b386689ab2d469ea1ff9eb423ac048549f7542c5) |
| exploitbench | linted | 16/17 | 6/6 | 3/3 | 4/4 | 3/4 | [`ccdd13a`](https://github.com/ChaoticCooties/exploitbench-eval/tree/ccdd13a128cf4dd25c720e8bf1f13d2867b6ba23) |
| frames | linted | 6/17 | 1/4 | 3/3 | 0/7 | 2/3 | [`2fbb1a1`](https://github.com/sahil350/frames-eval/tree/2fbb1a123431d559180547e325f0765d97ab2a39) |
| hangman-bench | linted | 12/15 | 3/4 | 2/3 | 4/5 | 3/3 | [`9f1f396`](https://github.com/MattFisher/hangman-bench/tree/9f1f396e68191eb5ec99dbffbc6fea63609bd0b6) |
| inspect-india-bharatbbq | linted | 8/12 | 2/4 | 3/3 | 1/2 | 2/3 | [`9c2e0bd`](https://github.com/MetaFazer/inspect-india-evals/tree/9c2e0bd9d8089444751ede080367dcc4983b9dc2) |
| inspect-india-cultural_knowledge | linted | 9/13 | 2/4 | 3/3 | 2/3 | 2/3 | [`9c2e0bd`](https://github.com/MetaFazer/inspect-india-evals/tree/9c2e0bd9d8089444751ede080367dcc4983b9dc2) |
| inspect-india-dpi_safety | linted | 8/13 | 2/4 | 3/3 | 1/3 | 2/3 | [`9c2e0bd`](https://github.com/MetaFazer/inspect-india-evals/tree/9c2e0bd9d8089444751ede080367dcc4983b9dc2) |
| inspect-india-jailbreak_safety | linted | 8/13 | 2/4 | 3/3 | 1/3 | 2/3 | [`9c2e0bd`](https://github.com/MetaFazer/inspect-india-evals/tree/9c2e0bd9d8089444751ede080367dcc4983b9dc2) |
| inspect-india-multilingual | linted | 8/13 | 2/4 | 3/3 | 1/3 | 2/3 | [`9c2e0bd`](https://github.com/MetaFazer/inspect-india-evals/tree/9c2e0bd9d8089444751ede080367dcc4983b9dc2) |
| inspect-india-multilingual_safety | linted | 8/13 | 2/4 | 3/3 | 1/3 | 2/3 | [`9c2e0bd`](https://github.com/MetaFazer/inspect-india-evals/tree/9c2e0bd9d8089444751ede080367dcc4983b9dc2) |
| lab_bench_2 | linted | 18/21 | 6/6 | 2/4 | 5/6 | 5/5 | [`081864a`](https://github.com/Generality-Labs/lab-bench/tree/081864af494b180ecf6aae3f7333e384c0d227af) |
| machiavelli | unsupported_layout: src/machiavelli_task.py is not inside a package (no __init__.py next to it); inspect-evals-lint checks one package per evaluation | - | - | - | - | - | [`6c61494`](https://github.com/Plyb/inspect-machiavelli/tree/6c6149488e7d6ecc02df8ca0b14c7ba783f16715) |
| manager_coercion_benchmark | unsupported_layout: manager_coercion.py is not inside a package (no __init__.py next to it); inspect-evals-lint checks one package per evaluation | - | - | - | - | - | [`48d6185`](https://github.com/CompassionML/manager-coercion-bench/tree/48d6185a8fd1642cb6fb47fc6c30edcfdd31d8bb) |
| manta | clone_failed: git fetch failed: fatal: could not read Username for &#x27;https://github.com&#x27;: terminal prompts disabled | - | - | - | - | - | [`1100a0f`](https://github.com/Mycelium-tools/manta_benchmark/tree/1100a0f88110abe98fc08f2f43ac3a822818d4d3) |
| mcptox | linted | 13/16 | 2/4 | 3/3 | 5/5 | 3/4 | [`d45705b`](https://github.com/stefanoamorelli/inspect-evals-mcptox/tree/d45705b0a7ae6697c851e311187b06bf7488b13f) |
| medcalc-bench | linted | 11/15 | 4/5 | 3/3 | 1/4 | 3/3 | [`e497f0e`](https://github.com/azrabano23/medcalc-bench-inspect/tree/e497f0e327b2e9245f3e832badb320ce84d6ddb5) |
| monitorbench-goal-sandbag-math | linted | 12/15 | 2/4 | 3/3 | 4/4 | 3/4 | [`e2e7b91`](https://github.com/semsorock/inspect-evals-monitor-bench/tree/e2e7b91a84d21e7cb374d59d49dbd25c3f40514f) |
| monitorbench-steganography | linted | 14/16 | 4/5 | 3/3 | 4/4 | 3/4 | [`7ef6d47`](https://github.com/semsorock/inspect-evals-monitor-bench/tree/7ef6d47219bbcca636071d5becbd572f4a4497a9) |
| narcbench | linted | 9/13 | 3/4 | 2/3 | 1/3 | 3/3 | [`d1c33d1`](https://github.com/shubhangithub/collusionguard/tree/d1c33d1041c3efdcb3e7a6a131f2160e03dfaed2) |
| openbookqa | linted | 12/13 | 3/4 | 3/3 | 3/3 | 3/3 | [`52222db`](https://github.com/Sammy-Dabbas/openbookqa-eval/tree/52222db933d8ec8a3bbfbcd06cd065899c829680) |
| or_bench | linted | 14/17 | 6/6 | 3/3 | 2/4 | 3/4 | [`8757ec4`](https://github.com/haeliotang/inspect-evals-orbench/tree/8757ec41608f3930e3c2bc4d5619d09a2381727a) |
| patcheval | linted | 10/16 | 2/4 | 2/3 | 2/5 | 4/4 | [`c8cc29e`](https://github.com/bytedance/PatchEval/tree/c8cc29e5609652c89b4987e1a466b1fb26f96426) |
| perspective_gap | linted | 10/18 | 4/5 | 3/3 | 0/7 | 3/3 | [`9ebdf21`](https://github.com/WhymustIhaveaname/PerspectiveGap-inspect/tree/9ebdf214922cf6d2f2306d03b9f3b4569e496703) |
| pinchbench | linted | 10/18 | 4/5 | 3/3 | 0/7 | 3/3 | [`1acc83d`](https://github.com/zytoh0/pinch-wildclawbench-inspect/tree/1acc83dbdc497d966d084d204adcbffe2d1d8aaa) |
| salad-bench | linted | 10/14 | 3/4 | 3/3 | 2/4 | 2/3 | [`e85b9fe`](https://github.com/WatchTree-19/inspect-salad-bench/tree/e85b9feb8d024890874694beb32e4bbf4564f169) |
| sycobench-600 | linted | 11/14 | 2/4 | 3/3 | 3/4 | 3/3 | [`5219abd`](https://github.com/debu-sinha/sycobench-600/tree/5219abda88de91300adcfefa37c3a824f0f103de) |
| tarantubench | linted | 9/18 | 2/4 | 3/3 | 0/7 | 4/4 | [`7bc03a2`](https://github.com/Trivulzianus/TarantuBench/tree/7bc03a2e57fd68a238ae621eeb6ae856fea77682) |
| wildclawbench | linted | 10/18 | 4/5 | 3/3 | 0/7 | 3/3 | [`1acc83d`](https://github.com/zytoh0/pinch-wildclawbench-inspect/tree/1acc83dbdc497d966d084d204adcbffe2d1d8aaa) |

## Embedding a badge

Replace `<id>` with the register entry id; `lint.json` may be swapped for `file_structure.json`, `code_quality.json`, `tests.json` or `best_practices.json`.

```markdown
![inspect-evals lint](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/ArcadiaImpact/inspect-evals-actions/register-lint/badges/<id>/lint.json)
```
