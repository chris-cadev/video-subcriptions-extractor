import click

@click.command()
@click.version_option("0.1.0", prog_name="YT Channel Video Extractor")
def cli():
    print('hi')

if __name__ == '__main__':
    cli()