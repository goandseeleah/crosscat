#
#   Copyright (c) 2010-2013, MIT Probabilistic Computing Project
#
#   Lead Developers: Dan Lovell and Jay Baxter
#   Authors: Dan Lovell, Baxter Eaves, Jay Baxter, Vikash Mansinghka
#   Research Leads: Vikash Mansinghka, Patrick Shafto
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
import multiprocessing
import collections
import functools
import operator
import re
import os
#
import numpy
import pylab
#
import crosscat.LocalEngine as LE
import crosscat.utils.data_utils as du
import crosscat.utils.file_utils as fu
import crosscat.utils.plot_utils as pu
import crosscat.tests.quality_tests.quality_test_utils as qtu


image_format = 'png'

def determine_Q(M_c, query_names, num_rows, impute_row=None):
    name_to_idx = M_c['name_to_idx']
    query_col_indices = [name_to_idx[colname] for colname in query_names]
    row_idx = num_rows + 1 if impute_row is None else impute_row
    Q = [(row_idx, col_idx) for col_idx in query_col_indices]
    return Q

def sample_T(engine, M_c, X_L, X_D):
    num_rows = len(X_D[0])
    num_cols = len(X_L['column_partition']['assignments'])
    query_cols = range(num_cols)
    col_names = numpy.array([M_c['idx_to_name'][str(col_idx)] for col_idx in range(num_cols)])
    query_names = col_names[query_cols]
    generated_T = []
    for row_i in range(num_rows):
        Q = determine_Q(M_c, query_names, row_i)
        sample = engine.simple_predictive_sample(M_c, X_L, X_D, None, Q, 1)[0]
        generated_T.append(sample)
    return generated_T

def collect_diagnostics(X_L, diagnostics_data, diagnostics_funcs):
    for key, func in diagnostics_funcs.iteritems():
        diagnostics_data[key].append(func(X_L))
    return diagnostics_data

def generate_diagnostics_funcs_for_column(X_L, column_idx):
    keys = set(X_L['column_hypers'][column_idx].keys())
    keys.discard('fixed')
    keys.discard('K')
    def helper(column_idx, key):
        func_name = 'col_%s_%s' % (column_idx, key)
        func = lambda X_L: X_L['column_hypers'][column_idx][key]
        return func_name, func
    diagnostics_funcs = { helper(column_idx, key) for key in keys }
    return diagnostics_funcs

def run_geweke_chain_iter(engine, M_c, T, X_L, X_D, diagnostics_data,
        diagnostics_funcs, specified_s_grid, specified_mu_grid,
        ):
    X_L, X_D = engine.analyze(M_c, T, X_L, X_D,
                specified_s_grid=specified_s_grid,
                specified_mu_grid=specified_mu_grid,
                )
    diagnostics_data = collect_diagnostics(X_L, diagnostics_data,
            diagnostics_funcs)
    T = sample_T(engine, M_c, X_L, X_D)
    return M_c, T, X_L, X_D

def arbitrate_plot_rand_idx(plot_rand_idx, num_iters):
    if plot_rand_idx is not None:
        if type(plot_rand_idx) == bool:
            if plot_rand_idx:
                plot_rand_idx = numpy.random.randint(num_iters)
            else:
                plot_rand_idx = None
                pass
            pass
        pass
    return plot_rand_idx

get_column_crp_alpha = lambda X_L: X_L['column_partition']['hypers']['alpha']
get_view_0_crp_alpha = lambda X_L: X_L['view_state'][0]['row_partition_model']['hypers']['alpha']
default_diagnostics_funcs = dict(
        column_crp_alpha=get_column_crp_alpha,
        view_0_crp_alpha=get_view_0_crp_alpha,
        )
def generate_diagnostics_funcs(X_L, probe_columns):
    diagnostics_funcs = default_diagnostics_funcs.copy()
    for probe_column in probe_columns:
        funcs_to_add = generate_diagnostics_funcs_for_column(X_L, probe_column)
        diagnostics_funcs.update(funcs_to_add)
        pass
    return diagnostics_funcs

def run_geweke_chain(seed, M_c, T, num_iters,
        probe_columns=(0,), specified_s_grid=(), specified_mu_grid=(),
        plot_rand_idx=None,
        ):
    plot_rand_idx = arbitrate_plot_rand_idx(plot_rand_idx, num_iters)
    engine = LE.LocalEngine(seed)
    M_r = du.gen_M_r_from_T(T)
    X_L, X_D = engine.initialize(M_c, M_r, T, 'from_the_prior')
    diagnostics_funcs = generate_diagnostics_funcs(X_L, probe_columns)
    diagnostics_data = collections.defaultdict(list)
    for idx in range(num_iters):
        M_c, T, X_L, X_D = run_geweke_chain_iter(engine, M_c, T, X_L, X_D, diagnostics_data,
                diagnostics_funcs, specified_s_grid, specified_mu_grid)
        if idx == plot_rand_idx:
            # This DOESN'T work with multithreading
            filename = 'T_%s.%s' % (idx, image_format)
            pu.plot_views(numpy.array(T), X_D, X_L, M_c, filename=filename, dir='',
                    close=True)
            pass
        pass
    return diagnostics_data

def run_geweke(M_c, T, num_chains, num_iters, probe_columns,
        specified_s_grid, specified_mu_grid):
    # specify multiprocessing or not by setting mapper
    mapper, pool = get_mapper(num_chains)
    # run geweke: transition-erase loop
    helper = functools.partial(run_geweke_chain, M_c=M_c, T=T, num_iters=num_iters,
            probe_columns=probe_columns,
            specified_s_grid=s_grid,
            specified_mu_grid=mu_grid,
            # this breaks with multiprocessing
            plot_rand_idx=(num_chains==1),
            )
    seeds = range(num_chains)
    diagnostics_data_list = mapper(helper, seeds)
    # if pool is not None:
    #     pool.close(); pool.join()
    return diagnostics_data_list

def _forward_sample_from_prior(inf_seed_and_n_samples, M_c, T,
        probe_columns=(0,), specified_s_grid=(), specified_mu_grid=(),
        ):
    inf_seed, n_samples = inf_seed_and_n_samples
    T = numpy.zeros(numpy.array(T).shape).tolist()
    M_r = du.gen_M_r_from_T(T)
    engine = LE.LocalEngine(inf_seed)
    diagnostics_data = collections.defaultdict(list)
    diagnostics_funcs = None
    for sample_idx in range(n_samples):
        X_L, X_D = engine.initialize(M_c, M_r, T,
                specified_s_grid=specified_s_grid,
                specified_mu_grid=specified_mu_grid,
                )
        if diagnostics_funcs is None:
            diagnostics_funcs = generate_diagnostics_funcs(X_L, probe_columns)
        diagnostics_data = collect_diagnostics(X_L, diagnostics_data,
                diagnostics_funcs)
        pass
    return diagnostics_data

def get_n_samples_per_worker(n_samples, cpu_count):
    n_samples_per_worker = n_samples / cpu_count
    ret_list = numpy.array([n_samples_per_worker] * cpu_count)
    delta = n_samples - n_samples_per_worker * cpu_count
    ret_list[range(delta)] += 1
    return ret_list

def forward_sample_from_prior(inf_seed, n_samples, M_c, T,
        probe_columns=(0,), specified_s_grid=(), specified_mu_grid=(),
        do_multiprocessing=True,
        ):
    helper = functools.partial(_forward_sample_from_prior, M_c=M_c, T=T,
            probe_columns=probe_columns,
            specified_s_grid=specified_s_grid,
            specified_mu_grid=specified_mu_grid,
            )
    cpu_count, mapper, pool = 1, map, None
    if do_multiprocessing:
        cpu_count = multiprocessing.cpu_count()
        pool = multiprocessing.Pool()
        mapper = pool.map
        pass
    seeds = numpy.random.randint(32676, size=cpu_count)
    n_samples_list = get_n_samples_per_worker(n_samples, cpu_count)
    forward_sample_data_list = mapper(helper, zip(seeds, n_samples_list))
    forward_sample_data = condense_diagnostics_data_list(forward_sample_data_list)
    return forward_sample_data

def condense_diagnostics_data_list(diagnostics_data_list):
    def get_key_condensed(key):
        get_key = lambda x: x.get(key)
        return reduce(operator.add, map(get_key, diagnostics_data_list))
    keys = diagnostics_data_list[0].keys()
    return { key : get_key_condensed(key) for key in keys}

def is_eps(data):
    data = numpy.array(data)
    return (0 < data) & (data < 1E-100)

def filter_eps(data):
    data = numpy.array(data)
    return data[~is_eps(data)]

def clip_extremes(data):
    data = numpy.array(data)
    percentiles = [.5, 99.5]
    lower, upper = numpy.percentile(data, percentiles)
    return data.clip(lower, upper)

def generate_log_bins(data, n_bins=31):
    data = filter_eps(data)
    log_min, log_max = numpy.log(min(data)), numpy.log(max(data))
    return numpy.exp(numpy.linspace(log_min, log_max, n_bins))

def generate_bins_unique(data):
    data = filter_eps(data)
    bins = sorted(set(data))
    delta = bins[-1] - bins[-2]
    bins.append(bins[-1] + delta)
    return bins

def do_hist_labelling(variable_name):
    title_str = 'Histogram for %s' % variable_name
    pylab.title(title_str)
    pylab.xlabel(variable_name)
    pylab.ylabel('frequency')
    return

def do_log_hist_bin_unique(variable_name, diagnostics_data, new_figure=True,
        do_labelling=True,
        ):
    data = diagnostics_data[variable_name]
    bins = generate_bins_unique(data)
    if new_figure:
        pylab.figure()
    hist_ret = pylab.hist(data, bins=bins)
    if do_labelling:
        do_hist_labelling(variable_name)
    pylab.gca().set_xscale('log')
    return hist_ret

def do_hist(variable_name, diagnostics_data, n_bins=31, new_figure=True,
        do_labelling=True,
        ):
    data = diagnostics_data[variable_name]
    data = clip_extremes(data)
    if new_figure:
        pylab.figure()
    pylab.hist(data, bins=n_bins)
    if do_labelling:
        do_hist_labelling(variable_name)
    return

create_line = lambda (key, value): key + ' = ' + str(value)
def get_parameters_as_text(parameters):
    lines = map(create_line, parameters.iteritems())
    text = '\n'.join(lines)
    return text

def show_parameters(parameters):
    if len(parameters) == 0: return
    ax = pylab.gca()
    text = get_parameters_as_text(parameters)
    pylab.text(0, 1, text, transform=ax.transAxes,
            va='top', size='small', linespacing=1.0)
    return

def save_current_figure(filename_no_format, directory, close_after_save=True,
        format=image_format):
    fu.ensure_dir(directory)
    full_filename = os.path.join(directory, filename_no_format + '.' + format)
    pylab.savefig(full_filename)
    if close_after_save:
        pylab.close()
        pass
    return

hyper_name_mapper = dict(
        s='precision hyperparameter value',
        nu='precision hyperparameter psuedo count',
        mu='mean hyperparameter value',
        r='mean hyperparameter psuedo count',
        )
col_hyper_re = re.compile('^col_([^_]*)_(.*)$')
def map_variable_name(variable_name):
    mapped_variable_name = variable_name
    match = col_hyper_re.match(variable_name)
    if match is not None:
        column_idx, hyper_name = match.groups()
        mapped_hyper_name = hyper_name_mapper.get(hyper_name, hyper_name)
        mapped_variable_name = 'column %s %s' % (column_idx, mapped_hyper_name)
        pass
    return mapped_variable_name

plotter_lookup = collections.defaultdict(lambda: do_log_hist_bin_unique,
        col_0_s=do_hist,
        col_0_mu=do_hist,
        col_0_r=do_hist,
        col_0_nu=do_hist,
        )
def plot_diagnostic_data(forward_diagnostics_data, diagnostics_data_list, variable_name,
        parameters=None, save_kwargs=None):
    plotter = plotter_lookup[variable_name]
    mapped_variable_name = map_variable_name(variable_name)
    which_idx = numpy.random.randint(len(diagnostics_data_list))
    diagnostics_data = diagnostics_data_list[which_idx]
    forward = forward_diagnostics_data[variable_name]
    not_forward_list = [el[variable_name] for el in diagnostics_data_list]
    kl_series_list = [
            get_fixed_gibbs_kl_series(forward, not_forward)
            for not_forward in not_forward_list
            ]
    pylab.figure()
    #
    pylab.subplot(311)
    pylab.title('Geweke analysis for %s' % mapped_variable_name)
    plotter(variable_name, forward_diagnostics_data, new_figure=False,
            do_labelling=False)
    pylab.ylabel('Forward samples\n mass')
    #
    pylab.subplot(312)
    plotter(variable_name, diagnostics_data, new_figure=False,
            do_labelling=False)
    pylab.ylabel('Posterior samples\n mass')
    #
    pylab.subplot(313)
    map(pylab.plot, kl_series_list)
    show_parameters(parameters)
    pylab.xlabel('iteration')
    pylab.ylabel('KL')
    if parameters is not None:
        show_parameters(parameters)
        pass
    if save_kwargs is not None:
        filename = variable_name + '_hist'
        save_current_figure(filename, format=image_format, **save_kwargs)
        pass
    return kl_series_list

def plot_all_diagnostic_data(forward_diagnostics_data, diagnostics_data_list,
        parameters=None, save_kwargs=None):
    kl_series_list_dict = dict()
    for variable_name in forward_diagnostics_data:
        try:
            kl_series_list = plot_diagnostic_data(forward_diagnostics_data, diagnostics_data_list,
                    variable_name, parameters, save_kwargs)
            kl_series_list_dict[variable_name] = kl_series_list
        except Exception, e:
            print 'Failed to plot_diagnostic_data for %s' % variable_name
            print e
            pass
        pass
    return kl_series_list_dict

def plot_diagnostic_data_hist(diagnostics_data, parameters=None, save_kwargs=None):
    for variable_name in diagnostics_data.keys():
        plotter = plotter_lookup[variable_name]
        plotter(variable_name, diagnostics_data)
        if parameters is not None:
            show_parameters(parameters)
            pass
        if save_kwargs is not None:
            filename = variable_name + '_hist'
            save_current_figure(filename, format=image_format, **save_kwargs)
            pass
        pass
    return

def get_kl((max_idx, grid, true_series, inferred_series)):
    # assume grid, series{1,2} are numpy arrays; series{1,2} with same length
    kld = numpy.nan
    try:
        if len(grid) < 2:
            raise Exception()
        bins = numpy.append(grid, grid[-1] + numpy.diff(grid)[-1])
        true_density, binz = numpy.histogram(true_series[:max_idx], bins, density=True)
        inferred_density, binz = numpy.histogram(inferred_series[:max_idx], bins, density=True)
        true_has_support = sum(true_density==0) == 0
        inferred_has_support = sum(inferred_density==0) == 0
        if true_has_support and inferred_has_support:
            # inferred has support every true does
            log_true_density = numpy.log(true_density)
            log_inferred_density = numpy.log(inferred_density)
            kld = qtu.KL_divergence_arrays(grid, log_true_density,
                    log_inferred_density, False)
            pass
    except Exception, e:
        pass
    return kld

def get_kl_series(grid, _true, _inferred):
    pool = multiprocessing.Pool()
    mapper = pool.map
    _true[is_eps(_true)] = 0
    _inferred[is_eps(_inferred)] = 0
    start_at = 10
    N = len(_true)
    #
    ns = range(start_at, N + 1)
    arg_tuples = [(n, grid, _true, _inferred) for n in ns]
    prepend = [numpy.nan] * start_at
    append = mapper(get_kl, arg_tuples)
    kl_series = prepend + append
    #
    pool.close(); pool.join()
    return kl_series

def make_same_length(*args):
    return zip(*zip(*args))

def get_fixed_gibbs_kl_series(forward, not_forward):
    forward, not_forward = make_same_length(forward, not_forward)
    forward, not_forward = map(numpy.array, (forward, not_forward))
    grid = numpy.array(sorted(set(forward)))
    return get_kl_series(grid, forward, not_forward)

def generate_directory_name(directory_prefix='geweke_plots', **kwargs):
    generate_part = lambda (key, value): key + '=' + str(value)
    parts = map(generate_part, kwargs.iteritems())
    directory_name = '_'.join([directory_prefix, ''.join(parts)])
    return directory_name

def arbitrate_mu_s(num_rows, max_mu_grid=100, max_s_grid=None):
    if max_s_grid == -1:
        max_s_grid = (max_mu_grid ** 2.) / 3. * num_rows
    return max_mu_grid, max_s_grid

def get_mapper(num_chains):
    mapper, pool = map, None
    if num_chains != 1:
        pool = multiprocessing.Pool(num_chains)
        mapper = pool.map
    return mapper, pool

def arbitrate_num_chains(num_chains, num_iters):
    if num_chains != 1:
        if num_chains is None:
            num_chains = multiprocessing.cpu_count()
            pass
        num_iters = num_iters /num_chains
    return num_chains, num_iters

def write_parameters_to_text(filename, parameters, directory=''):
    full_filename = os.path.join(directory, filename)
    text = get_parameters_as_text(parameters)
    with open(full_filename, 'w') as fh:
        fh.writelines(text + '\n')
        pass
    return

def gen_M_c(cctypes, num_values_list):
    num_cols = len(cctypes)
    colnames = range(num_cols)
    col_indices = range(num_cols)
    def helper(cctype, num_values):
        metadata_generator = du.metadata_generator_lookup[cctype]
        faux_data = range(num_values)
        return metadata_generator(faux_data)
    #
    name_to_idx = dict(zip(colnames, col_indices))
    idx_to_name = dict(zip(map(str, col_indices), colnames))
    column_metadata = map(helper, cctypes, num_values_list)
    M_c = dict(
        name_to_idx=name_to_idx,
        idx_to_name=idx_to_name,
        column_metadata=column_metadata,
        )
    return M_c


if __name__ == '__main__':
    import argparse
    pylab.ion()
    pylab.show()
    # parse input
    parser = argparse.ArgumentParser()
    parser.add_argument('--num_rows', default=40, type=int)
    parser.add_argument('--num_cols', default=4, type=int)
    parser.add_argument('--inf_seed', default=0, type=int)
    parser.add_argument('--gen_seed', default=0, type=int)
    parser.add_argument('--num_chains', default=None, type=int)
    parser.add_argument('--num_iters', default=10000, type=int)
    parser.add_argument('--max_mu_grid', default=100, type=int)
    parser.add_argument('--max_s_grid', default=1000, type=int)
    args = parser.parse_args()
    #
    num_rows = args.num_rows
    num_cols = args.num_cols
    inf_seed = args.inf_seed
    gen_seed = args.gen_seed
    num_chains = args.num_chains
    num_iters = args.num_iters
    max_mu_grid = args.max_mu_grid
    max_s_grid = args.max_s_grid


    num_chains, num_iters = arbitrate_num_chains(num_chains, num_iters)
    total_num_iters = num_chains * num_iters
    probe_columns = (0, 1)


    cctypes = ['multinomial'] * num_cols
    cctypes[0] = 'continuous'
    num_values_list = [2] * num_cols
    M_c = gen_M_c(cctypes, num_values_list)
    T = numpy.zeros((num_rows, num_cols)).tolist()

    # specify grid
    max_mu_grid, max_s_grid = arbitrate_mu_s(num_rows, max_mu_grid, max_s_grid)
    # may be an issue if this n_grid doesn't match the other grids in the c++
    n_grid = 31
    #
    mu_grid = numpy.linspace(-max_mu_grid, max_mu_grid, n_grid)
    s_grid = numpy.linspace(0, max_s_grid, n_grid)

    # run geweke: forward sample only
    print 'generating forward samples'
    forward_diagnostics_data = forward_sample_from_prior(inf_seed,
            total_num_iters, M_c, T, probe_columns=probe_columns,
            specified_s_grid=s_grid, specified_mu_grid=mu_grid,
            do_multiprocessing=True,
            )

    # run geweke: transition-erase loop
    print 'generating posterior samples'
    diagnostics_data_list = run_geweke(M_c, T, num_chains, num_iters, probe_columns,
            s_grid, mu_grid)

    # save plots
    print 'saving plots'
    plot_parameters = dict(
            num_rows=num_rows,
            num_cols=num_cols,
            max_mu_grid=max_mu_grid,
            max_s_grid=max_s_grid,
            total_num_iters=total_num_iters,
            chain_num_iters=num_iters,
            num_chains=num_chains,
            )
    directory = generate_directory_name(**plot_parameters)
    save_kwargs = dict(directory=directory)
    kl_series_list_dict = plot_all_diagnostic_data(
            forward_diagnostics_data, diagnostics_data_list,
            plot_parameters, save_kwargs)

    # process and save summary data
    print 'saving summary data'
    get_final = lambda indexable: indexable[-1]
    final_kls = {
            key : map(get_final, value)
            for key, value in kl_series_list_dict.iteritems()
            }
    summary_kls = {
            key : numpy.mean(value)
            for key, value in final_kls.iteritems()
            }
    save_parameters = plot_parameters.copy()
    save_parameters['final_kls'] = final_kls
    save_parameters['summary_kls'] = summary_kls
    write_parameters_to_text('parameters.txt', save_parameters, directory=directory)
    fu.pickle(save_parameters, 'parameters.pkl', dir=directory)