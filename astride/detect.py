import os

import numpy as np
import pylab as pl

from skimage import measure
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from photutils.background import Background

from astride.utils.edge import EDGE


class Streak:
    def __init__(self, filename, bkg_box_size=50, contour_threshold=3.,
                 output_path=None):
        """
        Initialize the streak instance.
        :param filename: Fits filename.
        :param bkg_box_size: Box size for background estimation.
        :param contour_threshold: Threshold to search contours (i.e. edges of
        an input image)
        :param output_path: Path to save figures and output files. If None,
        the base filename is used as the folder name.
        """
        hdulist = fits.open(filename)
        raw_image = hdulist[0].data.astype(np.float64)
        hdulist.close()

        # Raw image.
        self.raw_image = raw_image
        # Background structure and background map
        self.__bkg = None
        self.background_map = None
        # Background removed image.
        self.image = None
        # Raw edges
        self.raw_edges = None
        # Filtered edges, so streak, by their morphologies and
        # also connected (i.e. linked) by their slope.
        self.streaks = None

        # Other variables.
        self.bkg_box_size = bkg_box_size
        self.contour_threshold = contour_threshold

        # Set output path.
        if output_path is None:
            output_path = './%s/' % (os.path.basename(filename).split('.')[0])
        if output_path[-1] != '/':
            output_path += '/'
        self.output_path = output_path

        # For plotting.
        pl.rcParams['figure.figsize'] = [12, 9]

    def detect(self):
        """
        Run the pipeline to detect streaks.
        """
        self.__remove_background()
        #self.__detect_sources()
        self.__detect_streaks()

    def __remove_background(self):
        # Get background map and subtract.
        self.__bkg = Background(self.raw_image,
                                (self.bkg_box_size, self.bkg_box_size),
                                method='median')
        self.background_map = self.__bkg.background
        self.image = self.raw_image - self.background_map

    def __detect_streaks(self):
        # Find contours.
        # Returned contours is the list of [row, columns] (i.e. [y, x])
        bkg_rms = self.__bkg.background_rms_median
        contours = measure.find_contours(
            self.image, bkg_rms * self.contour_threshold, fully_connected='high'
                                         )

        # Quantify shapes of the contours and save them as 'edges'.
        edge = EDGE(contours)
        edge.quantify()
        self.raw_edges = edge.get_edges()

        # Filter the edges, so only streak remains.
        edge.filter_edges()
        edge.connect_edges()
        self.streaks = edge.get_edges()

    def __detect_sources(self):
        from photutils import daofind

        fwhm = 3.
        detection_threshold = 3.
        sources = daofind(self.image,
                          threshold=self.__bkg.background_rms_median *
                                    detection_threshold,
                          fwhm=fwhm)
        #sources = irafstarfind(data, threshold=std * detection_threshold, fwhm=FWHM)
        pl.plot(sources['xcentroid'], sources['ycentroid'], 'r.')

    def __find_box(self, n, edges, xs, ys):
        """
        Recursive function that defines a box surrounding
        one or more edges that are connected to each other.
        :param n: Index of edge currently checking.
        :param edges: edges.
        :param xs: x min and max coordinates.
        :param ys: y min and max coordinates.
        :return: x and y coordinates for plot plotting.
        """
        # Add current coordinates.
        current_edge = [edge for edge in edges if edge['index'] == n][0]
        current_edge['box_plotted'] = True
        xs.append([current_edge['x_min'], current_edge['x_max']])
        ys.append([current_edge['y_min'], current_edge['y_max']])

        # If connected with other edge.
        if current_edge['connectivity'] != -1:
            self.__find_box(current_edge['connectivity'], edges, xs, ys)
        # Otherwise.
        else:
            return xs, ys

    def plot_figures(self, cut_threshold=5.):
        """
        Save figures of detected streaks under the 'path' folder.
        :param cut_threshold: Threshold to cut image values to make it
        more visible.
        """
        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

        # Plot the image.
        plot_data = self.image.copy()
        mean, med, std = sigma_clipped_stats(self.image, sigma=3.0, iters=5)
        plot_data[np.where(self.image > med + cut_threshold * std)] = \
            med + cut_threshold * std
        plot_data[np.where(self.image < med - cut_threshold * std)] = \
            med - cut_threshold * std
        pl.imshow(plot_data, origin='lower', cmap='gray')

        edges = self.streaks
        # Plot all contours.
        for n, edge in enumerate(edges):
            pl.plot(edge['x'], edge['y'])
            pl.text(edge['x'][0], edge['y'][1],
                    '%d' % (edge['index']), color='b', fontsize=15)

        # Plot boxes.
        # Box margin in pixel.
        box_margin = 10
        for n, edge in enumerate(edges):
            # plot boxes around the edge.
            if not edge['box_plotted']:
                # Define the box to plot.
                xs = []
                ys = []
                self.__find_box(edge['index'], edges, xs, ys)
                x_min = max(np.min(xs) - box_margin, 0)
                x_max = min(np.max(xs) + box_margin, self.image.shape[0])
                y_min = max(np.min(ys) - box_margin, 0)
                y_max = min(np.max(ys) + box_margin, self.image.shape[1])
                box_x = [x_min, x_min, x_max, x_max]
                box_y = [y_min, y_max, y_max, y_min]
                pl.fill(box_x, box_y, ls='--', fill=False, ec='r', lw=2)
                edge['box_plotted'] = True

        pl.xlabel('X/pixel')
        pl.ylabel('Y/pixel')
        pl.axis([0, self.image.shape[0], 0, self.image.shape[1]])
        pl.savefig('%sall.png' % (self.output_path))

        # Plot all individual edges (connected).
        for n, edge in enumerate(edges):
            # Reset.
            edge['box_plotted'] = False

        for n, edge in enumerate(edges):
            if not edge['box_plotted']:
                # Define the box to plot.
                xs = []
                ys = []
                self.__find_box(edge['index'], edges, xs, ys)
                x_min = max(np.min(xs) - box_margin, 0)
                x_max = min(np.max(xs) + box_margin, self.image.shape[0])
                y_min = max(np.min(ys) - box_margin, 0)
                y_max = min(np.max(ys) + box_margin, self.image.shape[1])
                edge['box_plotted'] = True
                pl.axis([x_min, x_max, y_min, y_max])
                pl.savefig('%s%d.png' % (self.output_path, edge['index']))

        # Clear figure.
        pl.clf()

    def write_outputs(self):
        """
        Write information of detected streaks under the 'path' folder.
        :param path:
        """

        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

        fp = open('%sstreaks.txt' % (self.output_path), 'w')
        fp.writelines('#ID x_center y_center area perimeter shape_factor ' +
                      'radius_deviation slope_angle intercept connectivity\n')
        for n, edge in enumerate(self.streaks):
            line = '%2d %7.2f %7.2f %6.1f %6.1f %6.3f %6.2f %5.2f %7.2f %2d\n' % \
                   (
                       edge['index'], edge['x_center'], edge['y_center'],
                       edge['area'], edge['perimeter'], edge['shape_factor'],
                       edge['radius_deviation'], edge['slope_angle'],
                       edge['intercept'], edge['connectivity']
                   )
            fp.writelines(line)
        fp.close()

if __name__ == '__main__':
    import time

    #streak = Streak('/Users/kim/Dropbox/python/ASTRiDE/astride/datasets/samples/long.fits')
    streak = Streak('./datasets/samples/long.fits')

    start = time.time()
    streak.detect()
    end = time.time()

    print streak.streaks

    streak.plot_figures()
    streak.write_outputs()

    print '%.2f seconds' % (end - start)