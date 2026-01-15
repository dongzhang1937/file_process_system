.PHONY: build clean install test release

BINARY_NAME=mygo
VERSION=1.0.0
BUILD_TIME=$(shell date +%Y-%m-%d_%H:%M:%S)
LDFLAGS=-ldflags "-s -w -X main.Version=$(VERSION) -X main.BuildTime=$(BUILD_TIME)"

# 当前平台编译
build:
	go build $(LDFLAGS) -o $(BINARY_NAME) .

# 静态编译 (Linux) - 无任何外部依赖
build-static:
	CGO_ENABLED=0 go build $(LDFLAGS) -o $(BINARY_NAME) .

# 跨平台编译
build-linux:
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build $(LDFLAGS) -o $(BINARY_NAME)-linux-amd64 .

build-linux-arm:
	CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build $(LDFLAGS) -o $(BINARY_NAME)-linux-arm64 .

build-darwin:
	CGO_ENABLED=0 GOOS=darwin GOARCH=amd64 go build $(LDFLAGS) -o $(BINARY_NAME)-darwin-amd64 .

build-darwin-arm:
	CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build $(LDFLAGS) -o $(BINARY_NAME)-darwin-arm64 .

build-windows:
	CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build $(LDFLAGS) -o $(BINARY_NAME)-windows-amd64.exe .

# 编译所有平台
build-all: build-linux build-linux-arm build-darwin build-darwin-arm build-windows

# 发布版本 (编译+压缩)
release: build-all
	mkdir -p dist
	tar -czvf dist/$(BINARY_NAME)-$(VERSION)-linux-amd64.tar.gz $(BINARY_NAME)-linux-amd64
	tar -czvf dist/$(BINARY_NAME)-$(VERSION)-linux-arm64.tar.gz $(BINARY_NAME)-linux-arm64
	tar -czvf dist/$(BINARY_NAME)-$(VERSION)-darwin-amd64.tar.gz $(BINARY_NAME)-darwin-amd64
	tar -czvf dist/$(BINARY_NAME)-$(VERSION)-darwin-arm64.tar.gz $(BINARY_NAME)-darwin-arm64
	zip dist/$(BINARY_NAME)-$(VERSION)-windows-amd64.zip $(BINARY_NAME)-windows-amd64.exe
	rm -f $(BINARY_NAME)-linux-* $(BINARY_NAME)-darwin-* $(BINARY_NAME)-windows-*

install:
	go install $(LDFLAGS) .

clean:
	rm -f $(BINARY_NAME) $(BINARY_NAME)-*
	rm -rf dist/

test:
	go test -v ./...

deps:
	go mod tidy
	go mod download

run-mysql:
	./$(BINARY_NAME) -t mysql -H localhost -u root -p password -d test

run-pg:
	./$(BINARY_NAME) -t pg -H localhost -u postgres -p password -d postgres
