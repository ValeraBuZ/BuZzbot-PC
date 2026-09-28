import sys

if __name__ == '__main__':
    if '--check-installation' in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--check-installation', required=True)
        parser.add_argument('--image')
        parser.add_argument('--auction-image')
        options = parser.parse_args()
        from gear_value.diagnostics import check_installation
        sys.exit(check_installation(options.check_installation, options.image, options.auction_image))
    elif '--web' in sys.argv or '--no-browser' in sys.argv or '--port' in sys.argv:
        if '--web' in sys.argv: sys.argv.remove('--web')
        from gear_value.app import main
        main()
    else:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('--image')
        parser.add_argument('--data-dir')
        options = parser.parse_args()
        from gear_value.desktop import run
        run(options.data_dir, options.image)
