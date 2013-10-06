#ifndef GUARD_state_h
#define GUARD_state_h

#include <set>
#include <vector>
#include "View.h"
#include "utils.h"
#include "constants.h"
#include <fstream>
#include <iostream>
#include <algorithm>

#include <boost/numeric/ublas/io.hpp>
#include <boost/numeric/ublas/matrix_proxy.hpp>
typedef boost::numeric::ublas::matrix<double> MatrixD;

const static double r0_0 = 1.0;
const static double nu0_0 = 2.0;
const static double s0_0 = 2.0;
const static double mu0_0 = 0.0;

/**
 * A full CrossCat state.  This class is sufficient to draw a posterior sample.
 */
class State {
 public:

  /** Constructor for a fully specified state.
   *  Column and row partitionings are given, as well as all hyper parameters.
   *  \param data The data being modelled
   *  \param GLOBAL_COL_DATATYPES A vector of strings denoting column datatypes.
   *         Valid values are defined in constants.h
   *  \param GLOBAL_COL_MULTINOMIAL_COUNTS A vector of counts, denoting the number
   *         of possible values.
   *  \param global_row_indices A vector of ints, denoting the row indices
   *         of the data matrix passed in
   *  \param global_col_indices A vector of ints, denoting the column indices
   *         of the data matrix passed in
   *  \param HYPERS_M A map of column index to column hypers
   *  \param column_partition The partitioning of column indices.  Each partition
   *         denoting a view
   *  \param COLUMN_CRP_ALPHA The column CRP hyperparameter
   *  \param row_partition_v A vector of row partitionings.  One row partitioning
   *         for each element of column_partition
   *  \param row_crp_alpha_v The row CRP hyperparameters.  One for each element of
   *         column_partition
   *  \param N_GRID The number of grid points to use when gibbs sampling hyperparameters
   *  \param SEED The seed for the state's RNG
   */
  State(const MatrixD &data,
	std::vector<std::string> GLOBAL_COL_DATATYPES,
	std::vector<int> GLOBAL_COL_MULTINOMIAL_COUNTS,
	std::vector<int> global_row_indices,
	std::vector<int> global_col_indices,
	std::map<int, CM_Hypers > HYPERS_M,
	std::vector<std::vector<int> > column_partition,
	double COLUMN_CRP_ALPHA,
	std::vector<std::vector<std::vector<int> > > row_partition_v,
	std::vector<double> row_crp_alpha_v,
	int N_GRID=31, int SEED=0);

  /** Constructor for drawing a CrossCat state from the prior.
   *  Column and row partitionings are given, as well as all hyper parameters.
   *  \param data The data being modelled
   *  \param GLOBAL_COL_DATATYPES A vector of strings denoting column datatypes.
   *         Valid values are defined in constants.h
   *  \param GLOBAL_COL_MULTINOMIAL_COUNTS A vector of counts, denoting the number
   *         of possible values.
   *  \param global_row_indices A vector of ints, denoting the row indices
   *         of the data matrix passed in
   *  \param global_col_indices A vector of ints, denoting the column indices
   *         of the data matrix passed in
   *  \param col_initialization A string denoting which type of intialization
   *         to use for the column partitioning.  Valid values are defined in constants.h
   *  \param row_initialization A tring denoting which type of initialization
   *         to use for the row partitioning.  Valid values are defined in constants.h
   *  \param N_GRID The number of grid points to use when gibbs sampling hyperparameters
   *  \param SEED The seed for the state's RNG
   */
  State(const MatrixD &data,
	std::vector<std::string> GLOBAL_COL_DATATYPES,
	std::vector<int> GLOBAL_COL_MULTINOMIAL_COUNTS,
	std::vector<int> global_row_indices,
	std::vector<int> global_col_indices,
	std::string col_initialization=FROM_THE_PRIOR,
	std::string row_initialization="",
	int N_GRID=31, int SEED=0);

  ~State();

  //
  // getters
  //
  /**
   * \return The number of columns in the state
   */
  int get_num_cols() const;
  /**
   * \return The number of views (column partitions)
   */
  int get_num_views() const;
  /**
   * \return The number of columns in each view
   */
  std::vector<int> get_view_counts() const;
  /**
   * \return the column partition CRP hyperparameter
   */
  double get_column_crp_alpha() const;
  /**
   * \return The contribution of the column CRP marginal log probability
   * to the state's marginal log probability
   */
  double get_column_crp_score() const;
  /**
   * \return The contribution of each View's row clustering marginal log probability
   * to the state's marginal log probability
   */
  double get_data_score() const;
  /**
   * \return The state's marginal log probability
   */
  double get_marginal_logp() const;
  /**
   * \return The column indices in each column partition
   */
  std::map<int, std::vector<int> > get_column_groups() const;
  /**
   * \return A uniform random draw from [0, 1] using the state's rng
   */
  double draw_rand_u();
  /**
   * \return A random int from [0, max] using the state's rng
   */
  int draw_rand_i(int max=MAX_INT);

  //
  // helpers for API
  //
  /**
   * Get the hyperparameters used for the ith view
   * \return A map from hyperparameter name to value
   */
  std::map<std::string, double> get_row_partition_model_hypers_i(int view_idx) const;
  /**
   * Get the row partition model counts for the ith view
   * \return a vector of ints
   */
  std::vector<int> get_row_partition_model_counts_i(int view_idx) const;
  /**
   * Get the sufficient statistics for the ith view
   * \return A vector of cluster sufficient statistics
   */
  std::vector<std::vector<std::map<std::string, double> > > get_column_component_suffstats_i(int view_idx) const;
  /**
   * Get all the column component model hyperparameters in order
   */
  std::vector<CM_Hypers > get_column_hypers() const;
  /**
   * Get the hyperparameter associated with the column CRP model
   */
  std::map<std::string, double> get_column_partition_hypers() const;
  /**
   * Get a list denoting which view each column belongs to
   */
  std::vector<int> get_column_partition_assignments() const;
  /**
   * Get a list of counts of columns in each view
   */
  std::vector<int> get_column_partition_counts() const;
  /** 
   * Get a list of cluster memberships for each view.
   * Each cluster membership is itself a list denoting which cluster a row belongs to
   */
  std::vector<std::vector<int> > get_X_D() const;

  //
  // mutators
  //
  /**
   * Insert feature_data into the view specified by which_view.  feature_idx
   * is the column index to associate with it
   * \param feature_idx The column index that the view should associate with the data
   * \param feature_data The data that comprises the feature
   * \param which_view A reference to the view in which the feature should be added
   * \return The delta in the state's marginal log probability
   */
  double insert_feature(int feature_idx, std::vector<double> feature_data,
			View &which_view);
  /**
   * Gibbs sample which view to insert the feature into.
   * \param feature_idx The column index that the view should associate with the data
   * \param feature_data The data that comprises the feature
   * \param singleton_view A reference to an empty view to allow for creation of new views.
   *        Deleted internally if not used.
   */
  double sample_insert_feature(int feature_idx, std::vector<double> feature_data,
			       View &singleton_view);
  /**
   * Remove a feature from the state.
   * \param feature_idx The column index that the view should associaate with the data
   * \param feature_data The data that comprises the feature
   * \param p_singleton_view A pointer to the view the feature was removed from.
   *        This variables name is a bit of a misnomer: its not necessarily a singleton.
   *        Necesary to pass out for determining the marginal log probability delta
   */
  double remove_feature(int feature_idx, std::vector<double> feature_data,
			View* &p_singleton_view);
  /**
   * Gibbs sample a feature among the views, possibly creating a new view
   * \param feature_idx The column index that the view should associaate with the data
   * \param feature_data The data that comprises the feature
   */
  double transition_feature(int feature_idx, std::vector<double> feature_data);
  /**
   * Instantiate a new view object with properties matching the state
   * (datatypes, #rows, etc) and track in memeber variable views
   */
  View& get_new_view();
  /**
   * Get a particular view.
   */
  View& get_view(int view_idx);
  /**
   * Deallocate and remove the state if its empty.  Used as a helper for feature transitions
   */
  void remove_if_empty(View& which_view);
  /**
   * Deallocate all data structures.  For use before exiting.
   */
  void remove_all();
  /**
   * Stale function: don't use
   */
  double transition_view_i(int which_view,
			 std::map<int, std::vector<double> > row_data_map);
  /**
   * Stale function: don't use
   */
  double transition_view_i(int which_view, const MatrixD &data);
  /**
   * Stale function: don't use
   */
  double transition_views(const MatrixD &data);
  /**
   * Stale function: don't use
   */
  double transition_views_row_partition_hyper();
  /**
   * Stale function: don't use
   */
  double transition_views_col_hypers();
  /**
   * Stale function: don't use
   */
  double transition_views_zs(const MatrixD &data);
  /**
   * Stale function: don't use
   */
  double transition(const MatrixD &data);
  //
  /**
   * Gibbs sample column CRP hyperparameter over its hyper grid
   * \return The delta in the state's marginal log probability
   */
  double transition_column_crp_alpha();  
  /**
   * Gibbs sample view memebership of specified feature (column) indices
   * \return The delta in the state's marginal log probability
   */
  double transition_features(const MatrixD &data, std::vector<int> which_features);
  /**
   * Gibbs sample component model hyperparameters of specified feature (column) indices
   * \return The delta in the state's marginal log probability
   */
  double transition_column_hyperparameters(std::vector<int> which_cols);
  /**
   * Gibbs sample row partition CRP hyperparameter on views denoted by specified column indices
   * \return The delta in the state's marginal log probability
   */
  double transition_row_partition_hyperparameters(std::vector<int> which_cols);
  /**
   * Gibbs sample cluster membership of specified rows
   * \return The delta in the state's marginal log probability
   */
  double transition_row_partition_assignments(const MatrixD &data, std::vector<int> which_rows);
  //
  // calculators
  /**
   * \return The predictive log likelihood of a feature belonging to a particular view
   */
  double calc_feature_view_predictive_logp(std::vector<double> col_data,
					   std::string col_datatype,
					   View v,
					   double &crp_log_delta,
					   double &data_log_delta,
					   CM_Hypers hypers) const;
  /**
   * \return The predictive log likelihoods of a feature belonging to each view
   */
  std::vector<double> calc_feature_view_predictive_logps(std::vector<double> col_data, int global_col_idx) const;
  /**
   * \return The predictive log likelihood of a row having been generated by this state
   */
  double calc_row_predictive_logp(const std::vector<double> &in_vd);
  //
  // helpers
  /**
   * \return The log likelihood of the column CRP hyperparmeter value
   * given the state's column partitioning and the hyperprior on alpha
   * defined in numerics::calc_crp_alpha_hyperprior
   */
  double calc_column_crp_marginal() const;
  /**
   * \return The log likelihoods of the given column CRP hyperparmeter values
   * given the state's column partitioning and the hyperprior on alpha
   * defined in numerics::calc_crp_alpha_hyperprior
   */
  std::vector<double> calc_column_crp_marginals(std::vector<double> alphas_to_score) const;
  friend std::ostream& operator<<(std::ostream& os, const State& s);
  std::string to_string(std::string join_str="\n", bool top_level=false) const;
 private:
  // parameters
  std::map<int, std::string> global_col_datatypes;
  std::map<int, int> global_col_multinomial_counts;
  std::map<int, CM_Hypers > hypers_m;
  double column_crp_alpha;
  double column_crp_score;
  double data_score;
  // grids
  std::vector<double> column_crp_alpha_grid;
  std::vector<double> row_crp_alpha_grid;
  std::vector<double> r_grid;
  std::vector<double> nu_grid;
  std::vector<double> multinomial_alpha_grid;
  std::map<int, std::vector<double> > s_grids;
  std::map<int, std::vector<double> > mu_grids;
  // lookups
  std::set<View*> views;
  std::map<int, View*> view_lookup;  // global_column_index to View mapping
  // sub-objects
  RandomNumberGenerator rng;
  // resources
  void construct_base_hyper_grids(int num_rows, int num_cols, int N_GRID);
  void construct_column_hyper_grids(boost::numeric::ublas::matrix<double> data,
				    std::vector<int> global_col_indices,
				    std::vector<std::string> global_col_datatypes);
  CM_Hypers get_default_hypers() const;
  void init_base_hypers();
  CM_Hypers uniform_sample_hypers(int global_col_idx);
  void init_column_hypers(std::vector<int> global_col_indices);
  void init_views(const MatrixD &data,
		  std::map<int, std::string> global_col_datatypes,
		  std::vector<int> global_row_indices,
		  std::vector<int> global_col_indices,
		  std::vector<std::vector<int> > column_partition,
		  std::vector<std::vector<std::vector<int> > > row_partition_v,
		  std::vector<double> row_crp_alpha_v);
  void init_views(const MatrixD &data,
		  std::map<int, std::string> global_col_datatypes,
		  std::vector<int> global_row_indices,
		  std::vector<int> global_col_indices,
		  std::string col_initialization,
		  std::string row_initialization);
};

#endif // GUARD_state_h
