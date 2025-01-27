from typing import Any, Callable

import equinox as eqx
import equinox.nn as nn


class AuxData:
    """A simple container for auxiliary data"""

    def __init__(self):
        self.data = None

    def update(self, x: Any):
        """**Arguments:**

        - `x`: Any output generated by an intermediate layer that is meant to be stored
        """
        self.data = x


def _make_intermediate_layer_wrapper():
    aux = AuxData()

    class IntermediateWrapper(eqx.Module):
        layer: eqx.Module

        def __call__(self, x, *, key=None):
            out = self.layer(x, key=key)
            aux.update(out)
            return out

    return aux, IntermediateWrapper


def intermediate_layer_getter(
    model: "eqx.Module", get_target_layers: Callable
) -> "eqx.Module":
    """Wraps intermediate layers of a model for accessing intermediate activations. Based on a discussion
    [here](https://github.com/patrick-kidger/equinox/issues/186).

    !!! info
        Only supports storing the result of the most recent call. So, if the forward utilises the same layer multiple
        times, the returned intermediate value will be of the last call

    **Arguments:**

    - `model`: A PyTree representing the neural network model
    - `get_target_layers`: A callable function which returns a sequence
        of layers from the `model`

    **Returns:**
    The returned model will now return a `tuple` with

        0. The final output of `model`
        1. An ordered list of intermediate activations

    """
    target_layers = get_target_layers(model)
    auxs, wrappers = zip(
        *[_make_intermediate_layer_wrapper() for _ in range(len(target_layers))]
    )
    if isinstance(model, nn.Sequential):
        new_modules, updated_count = [], 0
        for idx, module in enumerate(model.layers):
            if idx in target_layers:
                new_modules.append(wrappers[updated_count](module))
                updated_count += 1
            else:
                new_modules.append(module)
        model = nn.Sequential(new_modules)
    else:
        model = eqx.tree_at(
            where=get_target_layers,
            pytree=model,
            replace=[
                wrapper(target_layer)
                for (wrapper, target_layer) in zip(wrappers, target_layers)
            ],
        )

    class IntermediateLayerGetter(eqx.Module):
        model: eqx.Module

        def __call__(self, x, *, key=None):
            out = self.model(x, key=key)
            return out, [aux.data for aux in auxs]

    return IntermediateLayerGetter(model)
