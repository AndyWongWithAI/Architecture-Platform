"""arch config — CLI 配置管理

子命令:
- show    显示当前配置(API Key 脱敏)
- set-url 设置服务端 URL
- set-key 设置 API Key
- set-format 设置输出格式
- path    显示配置文件路径
"""
from __future__ import annotations

import sys
from pathlib import Path

import click

from ..config import Config, config_path


@click.group(name="config", help="CLI 配置管理")
def cli():
    pass


@cli.command(name="show", help="显示当前配置")
def show_cmd():
    cfg = Config.load()
    click.echo(f"配置文件: {config_path()}")
    click.echo(f"  server.url:    {cfg.server_url}")
    click.echo(f"  server.api_key: {cfg.masked_key()}")
    click.echo(f"  output.format:  {cfg.output_format}")
    click.echo(f"  output.color:   {cfg.output_color}")


@cli.command(name="set-url", help="设置服务端 URL")
@click.argument("url")
def set_url_cmd(url):
    cfg = Config.load()
    cfg.server_url = url
    cfg.save()
    click.echo(f"✓ 已设置 server.url = {url}")


@cli.command(name="set-key", help="设置 API Key(传 '-' 清空)")
@click.argument("key")
def set_key_cmd(key):
    cfg = Config.load()
    cfg.api_key = "" if key == "-" else key
    cfg.save()
    click.echo(f"✓ 已设置 server.api_key = {cfg.masked_key()}")


@cli.command(name="set-format", help="设置输出格式(table / json)")
@click.argument("fmt", type=click.Choice(["table", "json"]))
def set_format_cmd(fmt):
    cfg = Config.load()
    cfg.output_format = fmt
    cfg.save()
    click.echo(f"✓ 已设置 output.format = {fmt}")


@cli.command(name="path", help="显示配置文件路径")
def path_cmd():
    p = config_path()
    click.echo(str(p))
    if p.exists():
        click.echo(f"(存在,{p.stat().st_size} bytes)")
    else:
        click.echo("(不存在)")