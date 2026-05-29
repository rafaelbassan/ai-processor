#!/bin/bash
# VectoSports AI Results Server - Development Helper Script

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

function print_header() {
    echo -e "\n${GREEN}================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}================================${NC}\n"
}

function print_step() {
    echo -e "${YELLOW}▶ $1${NC}"
}

function print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

function print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Get command
COMMAND=${1:-help}

case $COMMAND in
    build)
        print_header "Building Docker Image"
        print_step "Running: docker-compose build"
        docker-compose build
        print_success "Build completed"
        ;;
    
    up)
        print_header "Starting Docker Container"
        print_step "Running: docker-compose up -d"
        docker-compose up -d
        print_success "Container started"
        print_step "Waiting for service to be ready..."
        sleep 3
        curl -s http://localhost:8000/health > /dev/null && print_success "Service is ready!" || print_error "Service not ready yet"
        ;;
    
    down)
        print_header "Stopping Docker Container"
        print_step "Running: docker-compose down"
        docker-compose down
        print_success "Container stopped"
        ;;
    
    logs)
        print_header "Docker Logs"
        docker-compose logs -f vectosports-ai-server
        ;;
    
    logs-tail)
        print_header "Last 50 Lines of Logs"
        docker-compose logs --tail=50 vectosports-ai-server
        ;;
    
    restart)
        print_header "Restarting Docker Container"
        print_step "Stopping..."
        docker-compose down
        print_step "Starting..."
        docker-compose up -d
        sleep 2
        print_success "Container restarted"
        ;;
    
    clean)
        print_header "Cleaning Up"
        print_step "Removing containers..."
        docker-compose down
        print_step "Removing data..."
        rm -rf ./data/uploads/*
        mkdir -p ./data/uploads
        print_success "Cleanup completed"
        ;;
    
    test)
        print_header "Running Tests"
        if ! command -v python3 &> /dev/null; then
            print_error "Python 3 is not installed"
            exit 1
        fi
        
        print_step "Installing test dependencies..."
        python3 -m pip install requests -q
        
        print_step "Running test suite..."
        python3 test_api.py
        ;;
    
    health)
        print_header "Health Check"
        print_step "Checking server health..."
        curl -s http://localhost:8000/health | python3 -m json.tool || print_error "Server not responding"
        ;;
    
    debug-sessions)
        print_header "Active Upload Sessions"
        curl -s http://localhost:8000/debug/sessions | python3 -m json.tool || print_error "Cannot fetch sessions"
        ;;
    
    debug-jobs)
        print_header "Active Jobs"
        curl -s http://localhost:8000/debug/jobs | python3 -m json.tool || print_error "Cannot fetch jobs"
        ;;
    
    ps)
        print_header "Docker Container Status"
        docker-compose ps
        ;;
    
    shell)
        print_header "Opening Container Shell"
        docker-compose exec vectosports-ai-server /bin/bash
        ;;
    
    install-deps)
        print_header "Installing Python Dependencies"
        print_step "Installing local dependencies for development..."
        pip install -r api/requirements.txt
        print_success "Dependencies installed"
        ;;
    
    lint)
        print_header "Code Linting"
        if ! command -v pylint &> /dev/null; then
            print_step "Installing pylint..."
            pip install pylint -q
        fi
        print_step "Running pylint on server.py..."
        pylint api/server.py || true
        ;;
    
    format)
        print_header "Code Formatting"
        if ! command -v black &> /dev/null; then
            print_step "Installing black..."
            pip install black -q
        fi
        print_step "Formatting api/server.py..."
        black api/server.py
        print_success "Code formatted"
        ;;
    
    help|--help|-h)
        print_header "VectoSports AI Results Server - Helper Commands"
        echo "Usage: ./dev.sh [COMMAND]"
        echo ""
        echo "Commands:"
        echo "  build              Build Docker image"
        echo "  up                 Start Docker container"
        echo "  down               Stop Docker container"
        echo "  restart            Restart Docker container"
        echo "  logs               Show logs (follow)"
        echo "  logs-tail          Show last 50 lines of logs"
        echo "  clean              Stop container and clean data"
        echo "  ps                 Show container status"
        echo "  shell              Open container shell"
        echo ""
        echo "Testing & Debug:"
        echo "  test               Run full test suite"
        echo "  health             Check server health"
        echo "  debug-sessions     List active upload sessions"
        echo "  debug-jobs         List active jobs"
        echo ""
        echo "Development:"
        echo "  install-deps       Install Python dependencies"
        echo "  lint               Lint code with pylint"
        echo "  format             Format code with black"
        echo ""
        echo "Help:"
        echo "  help               Show this help message"
        echo ""
        print_success "For more info, see API_SERVER_README.md"
        ;;
    
    *)
        print_error "Unknown command: $COMMAND"
        echo "Run './dev.sh help' for available commands"
        exit 1
        ;;
esac
