"""Estilo comum dos gráficos (paleta de referência validada: azul/laranja/aqua)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TREATED = "#2a78d6"
CONTROL = "#eb6834"
THIRD = "#1baf7a"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
    "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
    "lines.linewidth": 2, "lines.markersize": 5, "legend.frameon": False,
})


def save(fig, path_stem):
    """Salva .png e .pdf."""
    for ext in ("png", "pdf"):
        fig.savefig(f"{path_stem}.{ext}")
    plt.close(fig)


def int_xaxis(ax):
    """Ticks inteiros no eixo x (tempo relativo)."""
    from matplotlib.ticker import MaxNLocator
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
