# acs-evals — the evaluation process, as commands.
#
# `make gate` is the whole thing: run the suite, check the generated eval tree,
# write the report. Everything else is a step of it, or a tool for working on
# the dataset.
#
# ACS_PLUGIN_ROOT selects the build under test. Leave it unset and the runner
# resolves the newest INSTALLED acs build, which is what a consumer actually
# runs; set it to point at a working tree instead.
#
#   make gate ACS_PLUGIN_ROOT=~/src/gms-marketplace/plugins/acs

PYTHON  ?= python3
RESULTS ?= results
JSON    ?= $(RESULTS)/latest.json
REPORT  ?= $(RESULTS)/report

.DEFAULT_GOAL := help
.PHONY: help gate eval report check list record clean verify-self

help: ## Show this help
	@printf '\nacs-evals — evaluation process\n\n'
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk -F':.*?## ' '{printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'
	@printf '\nBuild under test: %s\n\n' "$${ACS_PLUGIN_ROOT:-<newest installed acs>}"

gate: eval check report ## THE RELEASE GATE — run everything, fail on any red
	@printf '\nRelease gate complete. Report: $(REPORT).md / $(REPORT).html\n'

eval: ## Run the deterministic tier (208 cases, zero cost, no model)
	$(PYTHON) runner/run_golden.py --json $(JSON)

report: ## Render report.md + report.html from the last run
	$(PYTHON) runner/report.py --json $(JSON) --out $(REPORT)

check: ## Fail if evals/ is stale against dataset/routing.json
	$(PYTHON) runner/gen_plugin_eval.py --check

generate: ## Re-render evals/**/case.yaml from dataset/routing.json
	$(PYTHON) runner/gen_plugin_eval.py

list: ## List every case without running anything
	$(PYTHON) runner/run_golden.py --list

verify-self: ## Byte-compile the runner and parse every dataset file
	$(PYTHON) -m py_compile runner/*.py
	@$(PYTHON) -c "import glob,json,sys; \
	  [json.load(open(f)) for f in glob.glob('dataset/**/*.json', recursive=True)]; \
	  print('dataset: all JSON parses')"

record: ## DANGER — rewrite goldens from this build. Read the diff before committing.
	@printf 'This rewrites recorded expectations from the CURRENT build.\n'
	@printf 'Only do this when you have decided a behaviour change is intended.\n\n'
	$(PYTHON) runner/run_golden.py --record
	@printf '\nNow review EVERY line:  git diff dataset/cases/\n'

clean: ## Remove generated results and caches
	rm -rf $(RESULTS) runner/__pycache__
