# custom-shirts — pattern (FreeSewing) -> SVG / cut layout / 3D drape (Newton)
#
# Quick start:
#   make drape-gl      # interactive 3D cloth drape (opens a window; orbit w/ mouse)
#   make help          # list everything
#
# Override knobs on the command line, e.g.:
#   make drape-gl FRAMES=400 MAXAREA=70
#   make drape PIN_Y=45

PY      := .venv/bin/python
BLENDER := /opt/blender-5.0.1-linux-x64/blender

FRAMES  ?= 250     # sim frames (higher = more settled)
MAXAREA ?= 110     # cloth triangle max area, mm^2 (smaller = denser/slower)
BED_W   ?= 1400    # ShopBot bed width, mm (for `make nest`)
SA      ?= 10      # seam allowance, mm (for `make render`)
PIN_Y   ?= 45      # pin cloth above this height, mm (drape knob)
export PIN_Y

.DEFAULT_GOAL := help

# ---------------------------------------------------------------- pattern (2D)
.PHONY: render
render: ## Flat pattern -> dist/workshirt-all.svg + dist/parts/*.svg   (SA=..)
	SA=$(SA) node render.mjs

.PHONY: nest
nest: ## ShopBot cut layout -> dist/cut-layout.svg   (BED_W=.. SA=..)
	BED_W=$(BED_W) SA=$(SA) node nest.mjs

SPEC_SRC := export-garment.mjs src/index.mjs src/measurements.mjs src/options.mjs

.PHONY: garment
garment: dist/garment.json ## Build the SOURCE OF TRUTH -> dist/garment.json
dist/garment.json: $(SPEC_SRC)
	node export-garment.mjs

.PHONY: panels
panels: dist/panels.json ## (legacy) panel outlines -> dist/panels.json (assemble.py)
dist/panels.json: export-panels.mjs src/index.mjs src/measurements.mjs src/options.mjs
	node export-panels.mjs

# ---------------------------------------------------------------- 3D drape (Newton)
.PHONY: drape-gl
drape-gl: garment ## ** Interactive cloth drape ** — live GL window (orbit, pause)
	$(PY) newton_drape.py --viewer gl --num-frames $(FRAMES) --maxarea $(MAXAREA)

.PHONY: drape
drape: garment ## Headless drape -> OBJ -> Blender still (dist/newton/drape*.png)
	$(PY) newton_drape.py --viewer null --num-frames $(FRAMES) --maxarea $(MAXAREA)
	$(BLENDER) --background --python render_drape.py

.PHONY: drape-usd
drape-usd: garment ## Headless drape -> dist/newton/shirt_drape.usd (usdview/Blender)
	$(PY) newton_drape.py --viewer usd --output-path dist/newton/shirt_drape.usd \
	      --num-frames $(FRAMES) --maxarea $(MAXAREA)

# ---------------------------------------------------------------- static 3D (no sim)
.PHONY: assemble
assemble: panels ## Static geometric 3D assembly (no physics) -> dist/assembly.png
	$(BLENDER) --background --python assemble.py

# ------------------------------------------------ reverse: 3D garment -> 2D pattern
FLAT_MESH ?= dist/newton/shirt_front.obj   # a 3D panel mesh to unfold
MESH_IN   ?= dist/newton/shirt.obj         # a full garment mesh to segment
OUT       ?= dist/panels3d

.PHONY: flatten
flatten: ## Unfold a 3D panel mesh -> flat 2D pattern SVG (ARAP)  [FLAT_MESH=..]
	$(PY) tools/flatten.py $(FLAT_MESH)

.PHONY: segment
segment: ## Split a 3D garment mesh into panels by marked seams  [MESH_IN=.. OUT=..]
	$(BLENDER) --background --python tools/segment.py -- $(MESH_IN) $(OUT)

# ---------------------------------------------------------------- setup / misc
.PHONY: setup
setup: ## Create the .venv and install Newton + JS deps (one time)
	uv venv .venv --python 3.12
	uv pip install --python .venv/bin/python "newton[examples]" triangle libigl scipy cairosvg
	npm install

.PHONY: clean
clean: ## Remove generated output (dist/)
	rm -rf dist

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
