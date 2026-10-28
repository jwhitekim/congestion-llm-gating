.PHONY: run dash dash-build install

VIDEO ?= videos/department_store.mp4

run:
	PYTHONPATH=src python src/main.py $(VIDEO)

dash:
	npm --prefix dashboard run dev

build:
	npm --prefix dashboard run build

install:
	npm --prefix dashboard install
	@echo ""
	@echo "Python 의존성은 별도로 설치해야 합니다:"
	@echo "  pip install -r requirements.txt"
	@echo "  pip install --no-deps ocsort==0.0.2"
