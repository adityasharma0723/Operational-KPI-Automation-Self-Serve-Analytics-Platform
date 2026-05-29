import sys
import importlib

def test_import(lib_name):
    try:
        module = importlib.import_module(lib_name)
        version = getattr(module, '__version__', 'unknown')
        print(f"  [OK] {lib_name:<12} | Version: {version}")
        return True
    except ImportError:
        print(f"  [FAIL] {lib_name:<12} | NOT INSTALLED")
        return False

def main():
    print("=" * 60)
    print("OPERATIONAL KPI PLATFORM - DEVELOPMENT SETUP VERIFICATION")
    print("=" * 60)
    print(f"Python Version : {sys.version.split()[0]} ({sys.executable})")
    print("-" * 60)
    print("Checking core Python libraries:")
    
    libs = ['pandas', 'matplotlib', 'seaborn', 'scipy', 'openpyxl', 'notebook']
    all_ok = True
    
    for lib in libs:
        if not test_import(lib):
            all_ok = False
            
    print("-" * 60)
    if all_ok:
        print("SUCCESS: All core libraries are correctly installed and ready!")
        print("You are fully equipped to build data pipelines and notebooks!")
    else:
        print("WARNING: Some libraries failed to load. Please run pip install again.")
    print("=" * 60)

if __name__ == "__main__":
    main()
