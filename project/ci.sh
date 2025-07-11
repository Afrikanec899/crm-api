 #!/bin/sh

    set -o errexit
    set -o nounset

    : "${DJANGO_ENV:=development}"

    # Fail CI if `DJANGO_ENV` is not set to `development`:
    if [ "$DJANGO_ENV" != 'development' ]; then
      echo 'DJANGO_ENV is not set to development. Running tests is not safe.'
      exit 1
    fi

    pyclean () {
      # Clean cache:
      find . | grep -E '(__pycache__|\.py[cod]$)' | xargs rm -rf
    }

    run_tests () {
#      echo CHECKING TYPES
#      mypy --show-traceback .

      echo REFORMATTING CODE
      black -S -l 120 --exclude frontend --exclude migrations .

      # Check that all migrations worked fine:
      echo CHECKING MIGRATIONS
      python manage.py makemigrations --dry-run --check

      echo RUNNING PYTEST
      pytest  --ignore=frontend/
#      py.test -vv -s core/tests/test_views.py # --durations=0
    }

    # Remove any cache before the script:
    echo REMOVING CACHES
    pyclean

    # Clean everything up:
    trap pyclean EXIT INT TERM

    # Run the CI process:
    run_tests